import json
import logging
from typing import Dict, Set, Optional
from fastapi import WebSocket
from models.schemas import WebSocketMessage, MessageType

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages all active WebSocket connections."""

    def __init__(self):
        # user_id -> WebSocket
        self.active_connections: Dict[str, WebSocket] = {}
        # room_id -> set of user_ids
        self.room_connections: Dict[str, Set[str]] = {"lobby": set()}

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        self.active_connections[user_id] = websocket
        # Add to lobby by default
        self.room_connections.setdefault("lobby", set()).add(user_id)
        logger.info(f"User {user_id} connected. Total: {len(self.active_connections)}")

    def disconnect(self, user_id: str):
        self.active_connections.pop(user_id, None)
        # Remove from all rooms
        for room_id, members in self.room_connections.items():
            members.discard(user_id)
        logger.info(f"User {user_id} disconnected. Total: {len(self.active_connections)}")

    async def send_personal(self, user_id: str, message: dict):
        """Send message to a specific user."""
        ws = self.active_connections.get(user_id)
        if ws:
            try:
                await ws.send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"Error sending to {user_id}: {e}")
                self.disconnect(user_id)

    async def broadcast_to_room(self, room_id: str, message: dict, exclude_id: Optional[str] = None):
        """Broadcast message to all users in a room."""
        members = self.room_connections.get(room_id, set()).copy()
        for user_id in members:
            if user_id == exclude_id:
                continue
            await self.send_personal(user_id, message)

    async def broadcast_to_all(self, message: dict, exclude_id: Optional[str] = None):
        """Broadcast message to all connected users."""
        for user_id in list(self.active_connections.keys()):
            if user_id == exclude_id:
                continue
            await self.send_personal(user_id, message)

    def move_user_to_room(self, user_id: str, from_room: str, to_room: str):
        """Move user from one room to another."""
        self.room_connections.setdefault(from_room, set()).discard(user_id)
        self.room_connections.setdefault(to_room, set()).add(user_id)

    def add_room(self, room_id: str):
        self.room_connections.setdefault(room_id, set())

    def remove_room(self, room_id: str):
        self.room_connections.pop(room_id, None)

    def get_room_members(self, room_id: str) -> Set[str]:
        return self.room_connections.get(room_id, set()).copy()

    def get_user_count(self) -> int:
        return len(self.active_connections)

    def is_connected(self, user_id: str) -> bool:
        return user_id in self.active_connections
