""
WebSocket endpoints for real-time communication.
"""
import json
import logging
from typing import Dict, Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from jose import jwt, JWTError

from app.core.config import settings
from app.core.security import oauth2_scheme, get_current_user
from app.core.websocket import manager, websocket_handler
from app.models.user import User, UserRole
from app.schemas.websocket import WebSocketMessage, WebSocketAuth

router = APIRouter()
logger = logging.getLogger(__name__)

async def get_user_from_token(token: str, db) -> Optional[User]:
    """
    Get a user from a JWT token.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"verify_aud": False}
        )
        
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
            
        return await db.get(User, UUID(user_id))
        
    except (JWTError, ValidationError):
        raise credentials_exception

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = None,
    db = Depends(get_db),
):
    """
    WebSocket endpoint for real-time communication.
    
    Clients should provide a valid JWT token as a query parameter or in the
    Authorization header.
    
    Example connection URL:
    wss://yourapi.com/ws?token=your.jwt.token.here
    
    Or with Authorization header:
    wss://yourapi.com/ws
    Headers: {"Authorization": "Bearer your.jwt.token.here"}
    
    After connecting, clients can send and receive JSON messages with the following structure:
    {
        "type": "subscribe|unsubscribe|publish|auth",
        "channel": "channel_name",  // Required for subscribe/unsubscribe/publish
        "data": {}  // Optional data
    }
    
    Authentication is required before subscribing to channels or sending messages.
    """
    await websocket.accept()
    
    # Get token from query parameters or headers
    if not token:
        # Try to get token from headers
        headers = dict(websocket.scope.get("headers", []))
        auth_header = headers.get(b"authorization")
        
        if auth_header:
            scheme, _, token = auth_header.decode().partition(" ")
            if scheme.lower() != "bearer":
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return
    
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    # Authenticate user
    try:
        user = await get_user_from_token(token, db)
        if not user or not user.is_active:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
            
        logger.info(f"User {user.id} connected to WebSocket")
        
        # Subscribe to user's notification channel
        notification_channel = f"user:{user.id}"
        
        # Initial channels to subscribe to
        initial_channels = [
            notification_channel,  # User's personal notifications
            "global:announcements",  # Global announcements
        ]
        
        # Add role-specific channels
        if user.role == UserRole.READER:
            initial_channels.append("readers:updates")
        elif user.role == UserRole.ADMIN:
            initial_channels.append("admin:updates")
        
        # Handle the WebSocket connection
        await websocket_handler.handle_connection(
            websocket=websocket,
            user_id=user.id,
            initial_channels=initial_channels,
        )
        
    except (JWTError, HTTPException) as e:
        logger.warning(f"WebSocket authentication failed: {e}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)

@router.post("/ws/auth")
async def generate_websocket_token(
    current_user: User = Depends(get_current_user),
) -> WebSocketAuth:
    """
    Generate a WebSocket authentication token.
    
    This endpoint returns a JWT that can be used to authenticate a WebSocket connection.
    The token has a short expiration time (default: 5 minutes).
    """
    from datetime import datetime, timedelta, timezone
    
    # Create a token with a short expiration time
    expires_delta = timedelta(minutes=settings.WEBSOCKET_TOKEN_EXPIRE_MINUTES)
    expire = datetime.now(timezone.utc) + expires_delta
    
    to_encode = {
        "sub": str(current_user.id),
        "exp": expire,
        "type": "websocket",
        "role": current_user.role,
    }
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    
    return {
        "token": encoded_jwt,
        "expires_at": expire.isoformat(),
    }

# Helper functions for sending messages via WebSocket

async def send_user_notification(
    user_id: UUID,
    title: str,
    message: str,
    notification_type: str = "info",
    data: Optional[Dict[str, Any]] = None,
    action_url: Optional[str] = None,
) -> bool:
    """
    Send a notification to a specific user via WebSocket.
    
    Returns:
        bool: True if the message was sent, False if the user is not connected
    """
    notification = {
        "id": str(uuid4()),
        "title": title,
        "message": message,
        "type": notification_type,
        "data": data or {},
        "action_url": action_url,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "is_read": False,
    }
    
    # Send via WebSocket if user is connected
    sent = await manager.send_personal_message(
        user_id,
        {
            "type": "notification",
            "data": notification,
        }
    )
    
    # If user is not connected, the notification will be delivered when they reconnect
    return sent

async def broadcast_to_channel(
    channel: str,
    message: Dict[str, Any],
    exclude_user: Optional[UUID] = None,
) -> int:
    """
    Broadcast a message to all users subscribed to a channel.
    
    Args:
        channel: The channel to broadcast to
        message: The message to send (will be JSON-serialized)
        exclude_user: Optional user ID to exclude from the broadcast
        
    Returns:
        int: Number of recipients the message was sent to
    """
    return await manager.broadcast_to_channel(
        channel=channel,
        message=message,
        exclude=exclude_user,
    )

async def subscribe_user_to_channel(user_id: UUID, channel: str) -> None:
    """
    Subscribe a user to a channel.
    """
    manager.subscribe(user_id, channel)

async def unsubscribe_user_from_channel(user_id: UUID, channel: str) -> None:
    """
    Unsubscribe a user from a channel.
    """
    manager.unsubscribe(user_id, channel)
