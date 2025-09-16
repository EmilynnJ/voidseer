from fastapi import FastAPI, WebSocket, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.middleware.gzip import GZipMiddleware
from contextlib import asynccontextmanager
import asyncio
import json
import logging
from datetime import datetime
import stripe
from app.core.config import settings
from app.core.database import engine, Base
from app.websockets.connection_manager import ConnectionManager
from app.services.billing_service import BillingService
from app.services.notification_service import NotificationService
from app.services.payout_service import PayoutService
from app.services.session_service import SessionService
from app.services.email_service import EmailService
from app.api.v1.api import api_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

connection_manager = ConnectionManager()
billing_service = BillingService()
notification_service = NotificationService()
payout_service = PayoutService()
email_service = EmailService()
session_service = SessionService()

stripe.api_key = settings.STRIPE_SECRET_KEY

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up...")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    asyncio.create_task(billing_service.start_monitoring())
    asyncio.create_task(notification_service.start_scheduler())
    asyncio.create_task(payout_service.start_scheduler())

    yield

    logger.info("Shutting down...")
    await connection_manager.disconnect_all()
    await engine.dispose()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)
                
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
                
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await connection_manager.connect(websocket, client_id)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message["type"] == "chat_message":
                await connection_manager.broadcast_to_room(
                    message["room_id"],
                    json.dumps({
                        "type": "chat_message",
                        "from": client_id,
                        "content": message["content"],
                        "timestamp": datetime.utcnow().isoformat()
                    })
                )

            elif message["type"] == "typing":
                await connection_manager.broadcast_to_room(
                    message["room_id"],
                    json.dumps({
                        "type": "typing",
                        "from": client_id,
                        "is_typing": message["is_typing"]
                    }),
                    exclude=[client_id]
                )

    except WebSocketDisconnect:
        await connection_manager.disconnect(client_id)
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
        await connection_manager.disconnect(client_id)

@app.get("/health")
async def health_check():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

@app.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        await handle_checkout_session_completed(session)
    elif event["type"] == "invoice.payment_succeeded":
        invoice = event["data"]["object"]
        await handle_invoice_payment_succeeded(invoice)
    elif event["type"] == "invoice.payment_failed":
        invoice = event["data"]["object"]
        await handle_invoice_payment_failed(invoice)

    return {"status": "success"}

async def handle_checkout_session_completed(session: dict):
    pass

async def handle_invoice_payment_succeeded(invoice: dict):
    pass

async def handle_invoice_payment_failed(invoice: dict):
    pass

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

