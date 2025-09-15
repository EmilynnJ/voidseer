""
Pydantic models for WebSocket communication.
"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union
from uuid import UUID

from pydantic import BaseModel, Field, validator

class WebSocketMessageType(str, Enum):
    """Types of WebSocket messages."""
    AUTH = "auth"
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    MESSAGE = "message"
    NOTIFICATION = "notification"
    ERROR = "error"
    SUCCESS = "success"
    PING = "ping"
    PONG = "pong"

class WebSocketMessage(BaseModel):
    """Base WebSocket message model."""
    type: str = Field(..., description="Type of message")
    data: Optional[Dict[str, Any]] = Field(None, description="Message payload")
    request_id: Optional[str] = Field(None, description="Request ID for matching responses")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Message timestamp")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }
        use_enum_values = True

class WebSocketAuth(WebSocketMessage):
    """WebSocket authentication message."""
    type: Literal[WebSocketMessageType.AUTH] = WebSocketMessageType.AUTH
    token: str = Field(..., description="JWT token for authentication")

class WebSocketSubscribe(WebSocketMessage):
    """WebSocket subscribe message."""
    type: Literal[WebSocketMessageType.SUBSCRIBE] = WebSocketMessageType.SUBSCRIBE
    channels: List[str] = Field(..., description="Channels to subscribe to")

class WebSocketUnsubscribe(WebSocketMessage):
    """WebSocket unsubscribe message."""
    type: Literal[WebSocketMessageType.UNSUBSCRIBE] = WebSocketMessageType.UNSUBSCRIBE
    channels: List[str] = Field(..., description="Channels to unsubscribe from")

class WebSocketPing(WebSocketMessage):
    """WebSocket ping message for connection health checks."""
    type: Literal[WebSocketMessageType.PING] = WebSocketMessageType.PING

class WebSocketPong(WebSocketMessage):
    """WebSocket pong message in response to ping."""
    type: Literal[WebSocketMessageType.PONG] = WebSocketMessageType.PONG

class WebSocketNotification(WebSocketMessage):
    """WebSocket notification message."""
    type: Literal[WebSocketMessageType.NOTIFICATION] = WebSocketMessageType.NOTIFICATION
    notification_id: UUID = Field(..., description="Unique notification ID")
    title: str = Field(..., description="Notification title")
    message: str = Field(..., description="Notification message")
    notification_type: str = Field("info", description="Notification type (info, success, warning, error)")
    action_url: Optional[str] = Field(None, description="URL to navigate to when notification is clicked")
    is_read: bool = Field(False, description="Whether the notification has been read")

class WebSocketError(WebSocketMessage):
    """WebSocket error message."""
    type: Literal[WebSocketMessageType.ERROR] = WebSocketMessageType.ERROR
    code: str = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")

class WebSocketSuccess(WebSocketMessage):
    """WebSocket success message."""
    type: Literal[WebSocketMessageType.SUCCESS] = WebSocketMessageType.SUCCESS
    message: str = Field(..., description="Success message")
    data: Optional[Dict[str, Any]] = Field(None, description="Additional data")

class WebSocketChatMessage(WebSocketMessage):
    """WebSocket chat message."""
    type: Literal[WebSocketMessageType.MESSAGE] = WebSocketMessageType.MESSAGE
    channel: str = Field(..., description="Channel the message was sent to")
    sender: str = Field(..., description="ID of the user who sent the message")
    content: str = Field(..., description="Message content")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional message metadata")

# Union of all possible WebSocket message types
WebSocketMessageUnion = Union[
    WebSocketAuth,
    WebSocketSubscribe,
    WebSocketUnsubscribe,
    WebSocketPing,
    WebSocketPong,
    WebSocketNotification,
    WebSocketError,
    WebSocketSuccess,
    WebSocketChatMessage,
]

def parse_websocket_message(message: dict) -> WebSocketMessageUnion:
    """
    Parse a raw WebSocket message into the appropriate Pydantic model.
    
    Args:
        message: Raw WebSocket message as a dictionary
        
    Returns:
        Parsed WebSocket message
        
    Raises:
        ValueError: If the message type is unknown or invalid
    """
    message_type = message.get("type")
    
    if not message_type:
        raise ValueError("Message type is required")
    
    message_types = {
        WebSocketMessageType.AUTH: WebSocketAuth,
        WebSocketMessageType.SUBSCRIBE: WebSocketSubscribe,
        WebSocketMessageType.UNSUBSCRIBE: WebSocketUnsubscribe,
        WebSocketMessageType.PING: WebSocketPing,
        WebSocketMessageType.PONG: WebSocketPong,
        WebSocketMessageType.NOTIFICATION: WebSocketNotification,
        WebSocketMessageType.ERROR: WebSocketError,
        WebSocketMessageType.SUCCESS: WebSocketSuccess,
        WebSocketMessageType.MESSAGE: WebSocketChatMessage,
    }
    
    if message_type not in message_types:
        raise ValueError(f"Unknown message type: {message_type}")
    
    return message_types[message_type](**message)
