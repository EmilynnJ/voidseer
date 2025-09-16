from typing import Dict, List
from starlette.websockets import WebSocket

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}  # session_id -> list of websockets

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        self.active_connections[session_id].append(websocket)

    def disconnect(self, websocket: WebSocket, session_id: str):
        if session_id in self.active_connections:
            self.active_connections[session_id].remove(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast_to_session(self, message: str, session_id: str):
        if session_id in self.active_connections:
            for connection in self.active_connections[session_id]:
                await connection.send_text(message)

    async def handle_message(self, websocket: WebSocket, session_id: str, data: dict):
        message_type = data.get("type")
        if message_type == "chat":
            await self.broadcast_to_session(data["content"], session_id)
        elif message_type == "timer_update":
            await self.broadcast_to_session(f"Timer: {data['time']}", session_id)
        elif message_type == "end_session":
            await self.broadcast_to_session("Session ended", session_id)
            # Trigger billing
            pass  # Integrate with billing_service

manager = ConnectionManager()
