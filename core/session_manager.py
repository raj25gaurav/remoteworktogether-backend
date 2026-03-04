import uuid
import time
import logging
from typing import Dict, List, Optional
from models.schemas import User, UserStatus, AvatarType

logger = logging.getLogger(__name__)

USER_COLORS = [
    "#6366f1", "#8b5cf6", "#ec4899", "#14b8a6",
    "#f59e0b", "#10b981", "#3b82f6", "#f97316",
    "#ef4444", "#06b6d4", "#84cc16", "#a855f7",
]


class SessionManager:
    """Manages user sessions and presence."""

    def __init__(self):
        self.users: Dict[str, User] = {}
        self._color_index = 0

    def create_user(self, username: str, avatar: str = "astronaut") -> User:
        user_id = str(uuid.uuid4())[:12]
        color = USER_COLORS[self._color_index % len(USER_COLORS)]
        self._color_index += 1

        try:
            avatar_type = AvatarType(avatar)
        except ValueError:
            avatar_type = AvatarType.ASTRONAUT

        user = User(
            id=user_id,
            username=username,
            avatar=avatar_type,
            status=UserStatus.ONLINE,
            room_id="lobby",
            color=color,
        )
        self.users[user_id] = user
        logger.info(f"User created: {username} ({user_id})")
        return user

    def get_user(self, user_id: str) -> Optional[User]:
        return self.users.get(user_id)

    def remove_user(self, user_id: str):
        self.users.pop(user_id, None)
        logger.info(f"User removed: {user_id}")

    def update_user_room(self, user_id: str, room_id: str):
        user = self.users.get(user_id)
        if user:
            user.room_id = room_id

    def update_user_status(self, user_id: str, status: str):
        user = self.users.get(user_id)
        if user:
            try:
                user.status = UserStatus(status)
            except ValueError:
                pass

    def toggle_mute(self, user_id: str) -> bool:
        user = self.users.get(user_id)
        if user:
            user.is_muted = not user.is_muted
            return user.is_muted
        return False

    def toggle_camera(self, user_id: str) -> bool:
        user = self.users.get(user_id)
        if user:
            user.is_camera_off = not user.is_camera_off
            return user.is_camera_off
        return False

    def get_users_in_room(self, room_id: str) -> List[User]:
        return [u for u in self.users.values() if u.room_id == room_id]

    def get_all_users(self) -> List[User]:
        return list(self.users.values())

    def get_users_as_dict(self, room_id: Optional[str] = None) -> list:
        if room_id:
            return [u.model_dump() for u in self.get_users_in_room(room_id)]
        return [u.model_dump() for u in self.users.values()]
