import stripe
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.reading_session import ReadingSession
from app.models.user import User
from app.services.billing_service import calculate_ppm_charge

stripe.api_key = settings.STRIPE_SECRET_KEY

async def create_customer(user: User) -> str:
    customer = stripe.Customer.create(
        email=user.email,
        name=f"{user.first_name} {user.last_name}"
    )
    return customer.id

async def create_payment_intent(amount: int, customer_id: str, description: str) -> dict:
    try:
        intent = stripe.PaymentIntent.create(
            amount=amount,
            currency="usd",
            customer=customer_id,
            description=description,
            payment_method_types=["card"],
        )
        return intent
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))

async def confirm_payment_intent(payment_intent_id: str, payment_method: str) -> dict:
    try:
        intent = stripe.PaymentIntent.confirm(
            payment_intent_id,
            payment_method=payment_method,
        )
        return intent
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))

async def charge_for_session(db: AsyncSession, session: ReadingSession) -> dict:
    user = session.user
    if not user.stripe_customer_id:
        user.stripe_customer_id = await create_customer(user)
        await db.commit()

    charge_amount = await calculate_ppm_charge(session)
    intent = await create_payment_intent(charge_amount, user.stripe_customer_id, f"Charge for session {session.id}")
    return intent

async def handle_webhook(event: dict) -> None:
    event_type = event["type"]
    if event_type == "payment_intent.succeeded":
        # Update session status to paid
        pass  # Implement session update logic
    elif event_type == "payment_intent.payment_failed":
        # Handle failure, notify user
        pass  # Implement failure handling
    # Add more event handlers as needed

async def payout_to_reader(reader: User, amount: int) -> dict:
    if not reader.stripe_account_id:
        raise HTTPException(status_code=400, detail="Reader has no connected Stripe account")

    try:
        transfer = stripe.Transfer.create(
            amount=amount,
            currency="usd",
            destination=reader.stripe_account_id,
            description=f"Payout for reader {reader.id}"
        )
        return transfer
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))

async def create_connected_account(reader: User) -> str:
    account = stripe.Account.create(
        type="express",
        country="US",
        email=reader.email,
        capabilities={"card_payments": {"requested": True}, "transfers": {"requested": True}},
    )
    return account.id
