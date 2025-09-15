import json
import logging
from typing import Dict, List, Set, Optional
from fastapi import WebSocket
from collections import defaultdict

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.rooms: Dict[str, Set[str]] = defaultdict(set)  # room_id: set of client_ids
        self.user_rooms: Dict[str, Set[str]] = defaultdict(set)  # client_id: set of room_ids
        self.user_metadata: Dict[str, dict] = {}  # client_id: user_metadata

    async def connect(self, websocket: WebSocket, client_id: str, user_metadata: Optional[dict] = None):
        """Connect a client and store their metadata"""
        await websocket.accept()
        self.active_connections[client_id] = websocket
        self.user_rooms[client_id] = set()
        self.user_metadata[client_id] = user_metadata or {}
        logger.info(f"Client {client_id} connected")

    async def disconnect(self, client_id: str):
        """Disconnect a client and clean up"""
        if client_id in self.active_connections:
            # Leave all rooms
            if client_id in self.user_rooms:
                for room_id in list(self.user_rooms[client_id]):
                    await self.leave_room(client_id, room_id)
            
            # Clean up
            if client_id in self.user_metadata:
                del self.user_metadata[client_id]
            if client_id in self.user_rooms:
                del self.user_rooms[client_id]
            del self.active_connections[client_id]
            logger.info(f"Client {client_id} disconnected")

    async def send_personal_message(self, message: str, client_id: str):
        """Send a message to a specific client"""
        if client_id in self.active_connections:
            try:
                await self.active_connections[client_id].send_text(message)
            except Exception as e:
                logger.error(f"Error sending message to {client_id}: {str(e)}")
                await self.disconnect(client_id)

    async def broadcast_to_room(self, room_id: str, message: str, exclude: Optional[List[str]] = None):
        """Send a message to all clients in a room"""
        exclude = exclude or []
        if room_id in self.rooms:
            for client_id in list(self.rooms[room_id]):
                if client_id not in exclude:
                    await self.send_personal_message(message, client_id)

    async def join_room(self, client_id: str, room_id: str):
        """Add a client to a room"""
        if client_id in self.active_connections and room_id not in self.user_rooms[client_id]:
            self.rooms[room_id].add(client_id)
            self.user_rooms[client_id].add(room_id)
            logger.info(f"Client {client_id} joined room {room_id}")
            
            # Notify others in the room
            await self.broadcast_to_room(
                room_id,
                json.dumps({
                    "type": "user_joined",
                    "client_id": client_id,
                    "room_id": room_id,
                    "user_metadata": self.user_metadata.get(client_id, {})
                }),
                exclude=[client_id]
            )

    async def leave_room(self, client_id: str, room_id: str):
        """Remove a client from a room"""
        if client_id in self.active_connections and room_id in self.user_rooms[client_id]:
            self.rooms[room_id].discard(client_id)
            self.user_rooms[client_id].discard(room_id)
            
            # Clean up empty rooms
            if not self.rooms[room_id]:
                del self.rooms[room_id]
            
            logger.info(f"Client {client_id} left room {room_id}")
            
            # Notify others in the room
            await self.broadcast_to_room(
                room_id,
                json.dumps({
                    "type": "user_left",
                    "client_id": client_id,
                    "room_id": room_id
                })
            )

    async def disconnect_all(self):
        """Disconnect all clients"""
        for client_id in list(self.active_connections.keys()):
            await self.disconnect(client_id)

    def get_room_clients(self, room_id: str) -> Set[str]:
        """Get all client IDs in a room"""
        return self.rooms.get(room_id, set())
    
    def get_client_rooms(self, client_id: str) -> Set[str]:
        """Get all room IDs a client is in"""
        return self.user_rooms.get(client_id, set())
    
    def get_connected_clients(self) -> List[str]:
        """Get all connected client IDs"""
        return list(self.active_connections.keys())
