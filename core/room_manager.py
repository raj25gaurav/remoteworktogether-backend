import uuid
import logging
from typing import Dict, List, Optional
from models.schemas import Room, User

logger = logging.getLogger(__name__)

LOBBY_ID = "lobby"


class RoomManager:
    """Manages lobby and private cabins."""

    def __init__(self):
        self.rooms: Dict[str, Room] = {
            LOBBY_ID: Room(
                id=LOBBY_ID,
                name="Main Lobby",
                created_by="system",
                is_private=False,
                max_members=500,
                description="The main gathering space for everyone 🌟",
                emoji="🏠",
            )
        }

    def create_room(self, name: str, created_by: str, is_private: bool = True,
                    description: str = "", emoji: str = "🚪") -> Room:
        room_id = str(uuid.uuid4())[:8]
        room = Room(
            id=room_id,
            name=name,
            created_by=created_by,
            is_private=is_private,
            description=description,
            emoji=emoji,
        )
        self.rooms[room_id] = room
        logger.info(f"Room created: {name} ({room_id}) by {created_by}")
        return room

    def get_room(self, room_id: str) -> Optional[Room]:
        return self.rooms.get(room_id)

    def get_all_public_rooms(self) -> List[Room]:
        return [r for r in self.rooms.values() if not r.is_private or r.id == LOBBY_ID]

    def get_all_rooms(self) -> List[Room]:
        return list(self.rooms.values())

    def add_member(self, room_id: str, user_id: str) -> bool:
        room = self.rooms.get(room_id)
        if not room:
            return False
        if len(room.members) >= room.max_members:
            return False
        if user_id not in room.members:
            room.members.append(user_id)
        return True

    def remove_member(self, room_id: str, user_id: str):
        room = self.rooms.get(room_id)
        if room and user_id in room.members:
            room.members.remove(user_id)
        # Clean up empty private rooms
        if room and room.id != LOBBY_ID and room.is_private and not room.members:
            del self.rooms[room.id]
            logger.info(f"Empty private room {room.id} deleted.")

    def room_exists(self, room_id: str) -> bool:
        return room_id in self.rooms

    def can_join(self, room_id: str, user_id: str) -> bool:
        room = self.rooms.get(room_id)
        if not room:
            return False
        if room.is_private and user_id not in room.members and room.created_by != user_id:
            return False
        return len(room.members) < room.max_members

    def get_rooms_as_dict(self) -> list:
        return [r.model_dump() for r in self.rooms.values()]
