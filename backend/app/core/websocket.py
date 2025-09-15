""
WebSocket manager for handling real-time communication.
"""
import json
import logging
from typing import Dict, Set, Optional, Any, List
from uuid import UUID

from fastapi import WebSocket, WebSocketDisconnect, status
from fastapi.encoders import jsonable_encoder

from app.schemas.notification import NotificationResponse

logger = logging.getLogger(__name__)

class ConnectionManager:
    """
    Manages WebSocket connections and message broadcasting.
    """
    def __init__(self):
        # Maps user IDs to their active WebSocket connections
        self.active_connections: Dict[UUID, WebSocket] = {}
        
        # Maps user IDs to sets of channel names they're subscribed to
        self.user_subscriptions: Dict[UUID, Set[str]] = {}
        
        # Maps channel names to sets of user IDs subscribed to them
        self.channel_subscribers: Dict[str, Set[UUID]] = {}
    
    async def connect(self, websocket: WebSocket, user_id: UUID) -> None:
        """
        Accept a new WebSocket connection for a user.
        """
        # Close any existing connection for this user
        await self.disconnect(user_id)
        
        # Accept the new connection
        await websocket.accept()
        self.active_connections[user_id] = websocket
        self.user_subscriptions[user_id] = set()
        
        logger.info(f"User {user_id} connected to WebSocket")
    
    def disconnect(self, user_id: UUID) -> None:
        """
        Remove a user's WebSocket connection and clean up subscriptions.
        """
        if user_id in self.active_connections:
            # Remove from active connections
            del self.active_connections[user_id]
            
            # Remove from all channel subscriptions
            if user_id in self.user_subscriptions:
                for channel in list(self.user_subscriptions[user_id]):
                    self.unsubscribe(user_id, channel)
                del self.user_subscriptions[user_id]
            
            logger.info(f"User {user_id} disconnected from WebSocket")
    
    async def send_personal_message(self, user_id: UUID, message: Dict[str, Any]) -> bool:
        """
        Send a message to a specific user.
        
        Returns:
            bool: True if the message was sent, False if the user is not connected
        """
        if user_id not in self.active_connections:
            return False
        
        try:
            await self.active_connections[user_id].send_json(message)
            return True
        except Exception as e:
            logger.error(f"Error sending message to user {user_id}: {e}")
            self.disconnect(user_id)
            return False
    
    async def send_personal_notification(self, user_id: UUID, notification: Dict[str, Any]) -> bool:
        """
        Send a notification to a specific user.
        
        This is a convenience wrapper around send_personal_message that formats
        the message as a notification.
        """
        return await self.send_personal_message(
            user_id,
            {
                "type": "notification",
                "data": notification,
            }
        )
    
    async def broadcast_to_channel(self, channel: str, message: Dict[str, Any], exclude: Optional[UUID] = None) -> int:
        """
        Broadcast a message to all users subscribed to a channel.
        
        Args:
            channel: The channel to broadcast to
            message: The message to send (will be JSON-serialized)
            exclude: Optional user ID to exclude from the broadcast
            
        Returns:
            int: Number of recipients the message was sent to
        """
        if channel not in self.channel_subscribers:
            return 0
        
        recipients = 0
        
        # Convert message to JSON once for efficiency
        message_json = json.dumps(message)
        
        # Send to each subscriber
        for user_id in list(self.channel_subscribers[channel]):
            if user_id == exclude:
                continue
                
            if user_id in self.active_connections:
                try:
                    await self.active_connections[user_id].send_text(message_json)
                    recipients += 1
                except Exception as e:
                    logger.error(f"Error broadcasting to user {user_id}: {e}")
                    self.disconnect(user_id)
        
        return recipients
    
    def subscribe(self, user_id: UUID, channel: str) -> None:
        """
        Subscribe a user to a channel.
        """
        if user_id not in self.user_subscriptions:
            self.user_subscriptions[user_id] = set()
        
        if channel not in self.channel_subscribers:
            self.channel_subscribers[channel] = set()
        
        self.user_subscriptions[user_id].add(channel)
        self.channel_subscribers[channel].add(user_id)
        
        logger.debug(f"User {user_id} subscribed to channel '{channel}'")
    
    def unsubscribe(self, user_id: UUID, channel: str) -> None:
        """
        Unsubscribe a user from a channel.
        """
        if user_id in self.user_subscriptions and channel in self.user_subscriptions[user_id]:
            self.user_subscriptions[user_id].remove(channel)
            
            # Clean up empty user subscription sets
            if not self.user_subscriptions[user_id]:
                del self.user_subscriptions[user_id]
        
        if channel in self.channel_subscribers and user_id in self.channel_subscribers[channel]:
            self.channel_subscribers[channel].remove(user_id)
            
            # Clean up empty channel subscriber sets
            if not self.channel_subscribers[channel]:
                del self.channel_subscribers[channel]
        
        logger.debug(f"User {user_id} unsubscribed from channel '{channel}'")
    
    def unsubscribe_all(self, user_id: UUID) -> None:
        """
        Unsubscribe a user from all channels.
        """
        if user_id in self.user_subscriptions:
            for channel in list(self.user_subscriptions[user_id]):
                self.unsubscribe(user_id, channel)
    
    def get_connected_users(self) -> List[UUID]:
        """
        Get a list of currently connected user IDs.
        """
        return list(self.active_connections.keys())
    
    def is_connected(self, user_id: UUID) -> bool:
        """
        Check if a user is currently connected.
        """
        return user_id in self.active_connections
    
    def get_user_channels(self, user_id: UUID) -> Set[str]:
        """
        Get all channels a user is subscribed to.
        """
        return set(self.user_subscriptions.get(user_id, []))
    
    def get_channel_subscribers(self, channel: str) -> Set[UUID]:
        """
        Get all users subscribed to a channel.
        """
        return set(self.channel_subscribers.get(channel, set()))

# Global instance of the connection manager
manager = ConnectionManager()

# WebSocket endpoint handler
class WebSocketHandler:
    """
    Handles WebSocket connections and message routing.
    """
    def __init__(self, manager: ConnectionManager):
        self.manager = manager
    
    async def handle_connection(
        self,
        websocket: WebSocket,
        user_id: UUID,
        initial_channels: Optional[List[str]] = None
    ) -> None:
        """
        Handle a new WebSocket connection.
        
        Args:
            websocket: The WebSocket connection
            user_id: The authenticated user's ID
            initial_channels: Optional list of channels to subscribe to initially
        """
        # Connect the user
        await self.manager.connect(websocket, user_id)
        
        # Subscribe to initial channels
        if initial_channels:
            for channel in initial_channels:
                self.manager.subscribe(user_id, channel)
        
        try:
            # Keep the connection alive and process messages
            while True:
                data = await websocket.receive_text()
                
                try:
                    message = json.loads(data)
                    await self.handle_message(user_id, message)
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON received from user {user_id}")
                    await self.send_error(user_id, "Invalid message format")
                except Exception as e:
                    logger.error(f"Error processing message from user {user_id}: {e}")
                    await self.send_error(user_id, f"Error processing message: {str(e)}")
                    
        except WebSocketDisconnect:
            logger.info(f"User {user_id} disconnected")
        except Exception as e:
            logger.error(f"WebSocket error for user {user_id}: {e}")
        finally:
            # Clean up on disconnect
            self.manager.disconnect(user_id)
    
    async def handle_message(self, user_id: UUID, message: Dict[str, Any]) -> None:
        """
        Process an incoming WebSocket message.
        """
        if not isinstance(message, dict):
            raise ValueError("Message must be a JSON object")
        
        message_type = message.get("type")
        
        if message_type == "subscribe":
            # Handle channel subscription
            channel = message.get("channel")
            if not channel:
                raise ValueError("Channel name is required for subscription")
            
            self.manager.subscribe(user_id, channel)
            await self.send_success(user_id, f"Subscribed to channel '{channel}'")
            
        elif message_type == "unsubscribe":
            # Handle channel unsubscription
            channel = message.get("channel")
            if not channel:
                raise ValueError("Channel name is required for unsubscription")
            
            self.manager.unsubscribe(user_id, channel)
            await self.send_success(user_id, f"Unsubscribed from channel '{channel}'")
            
        elif message_type == "publish":
            # Handle message publishing to a channel
            channel = message.get("channel")
            data = message.get("data")
            
            if not channel:
                raise ValueError("Channel name is required for publishing")
            
            if data is None:
                raise ValueError("Message data is required")
            
            # Verify the user is subscribed to the channel
            if channel not in self.manager.get_user_channels(user_id):
                raise ValueError(f"Not subscribed to channel '{channel}'")
            
            # Broadcast the message to all other subscribers
            await self.manager.broadcast_to_channel(
                channel=channel,
                message={
                    "type": "message",
                    "channel": channel,
                    "sender": str(user_id),
                    "data": data,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                exclude=user_id  # Don't send back to the sender
            )
            
            await self.send_success(user_id, "Message published")
            
        else:
            raise ValueError(f"Unknown message type: {message_type}")
    
    async def send_error(self, user_id: UUID, message: str, code: str = "error") -> None:
        """
        Send an error message to a user.
        """
        await self.manager.send_personal_message(
            user_id,
            {
                "type": "error",
                "code": code,
                "message": message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
    
    async def send_success(self, user_id: UUID, message: str, data: Any = None) -> None:
        """
        Send a success message to a user.
        """
        response = {
            "type": "success",
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        if data is not None:
            response["data"] = data
        
        await self.manager.send_personal_message(user_id, response)

# Create a global instance of the WebSocket handler
websocket_handler = WebSocketHandler(manager)
