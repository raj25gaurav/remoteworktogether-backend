from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from enum import Enum


class MessageType(str, Enum):
    # Connection
    USER_JOIN = "user_join"
    USER_LEAVE = "user_leave"
    USER_LIST = "user_list"
    # Chat
    CHAT_MESSAGE = "chat_message"
    # Rooms
    ROOM_LIST = "room_list"
    ROOM_CREATE = "room_create"
    ROOM_JOIN = "room_join"
    ROOM_LEAVE = "room_leave"
    ROOM_INVITE = "room_invite"
    ROOM_UPDATE = "room_update"
    # Reactions
    REACTION = "reaction"
    GIF_REACTION = "gif_reaction"
    # WebRTC
    WEBRTC_OFFER = "webrtc_offer"
    WEBRTC_ANSWER = "webrtc_answer"
    WEBRTC_ICE = "webrtc_ice"
    # Status
    STATUS_UPDATE = "status_update"
    ERROR = "error"
    PING = "ping"
    PONG = "pong"


class UserStatus(str, Enum):
    ONLINE = "online"
    BUSY = "busy"
    AWAY = "away"
    FOCUS = "focus"


class AvatarType(str, Enum):
    ASTRONAUT = "astronaut"
    ROBOT = "robot"
    WIZARD = "wizard"
    NINJA = "ninja"
    SCIENTIST = "scientist"
    ARTIST = "artist"
    GAMER = "gamer"
    CHEF = "chef"


class User(BaseModel):
    id: str
    username: str
    avatar: AvatarType = AvatarType.ASTRONAUT
    status: UserStatus = UserStatus.ONLINE
    room_id: str = "lobby"
    is_muted: bool = False
    is_camera_off: bool = False
    color: str = "#6366f1"
    db_user_id: Optional[str] = None


class Room(BaseModel):
    id: str
    name: str
    created_by: str
    members: List[str] = []
    is_private: bool = False
    max_members: int = 20
    description: str = ""
    emoji: str = "🏠"


class WebSocketMessage(BaseModel):
    type: MessageType
    payload: Dict[str, Any] = {}
    sender_id: Optional[str] = None
    room_id: Optional[str] = None
    target_id: Optional[str] = None


class ChatMessage(BaseModel):
    id: str
    sender_id: str
    username: str
    content: str
    room_id: str
    timestamp: float
    message_type: str = "text"  # text | emoji | gif


class Reaction(BaseModel):
    sender_id: str
    username: str
    type: str  # emoji | gif
    content: str  # emoji char or gif URL
    room_id: str
    x: float = 50.0  # position percentage
    y: float = 50.0


class AIAvatarRequest(BaseModel):
    message: str
    user_id: str
    username: str
    room_id: str
    room_name: str
    room_members: List[str] = []
    conversation_history: List[Dict[str, str]] = []


class AIAvatarResponse(BaseModel):
    response: str
    emotion: str = "happy"
    suggestions: List[str] = []
