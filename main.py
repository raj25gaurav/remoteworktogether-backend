import os
import json
import time
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

from core.connection_manager import ConnectionManager
from core.room_manager import RoomManager
from core.session_manager import SessionManager
from core.reaction_handler import ReactionHandler
from models.schemas import MessageType, WebSocketMessage
from api.avatar_ai import router as avatar_router
from api.turn_credentials import router as turn_router

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Global managers
connection_manager = ConnectionManager()
room_manager = RoomManager()
session_manager = SessionManager()
reaction_handler = ReactionHandler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 RemoteWorkTogether server starting...")
    yield
    logger.info("👋 Server shutting down...")


app = FastAPI(
    title="RemoteWorkTogether API",
    description="Virtual work-from-home collaborative space",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow all origins for local development and deployed frontend
_allowed_origins = ["*"]

# (Optional: If we don't want to use "*", we could keep the list below)
# We will just use ["*"] as per the request to allow localhost reliably.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(avatar_router)
app.include_router(turn_router)


# ──────────────────────────────────────────────────────────────────────────────
# REST Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"message": "RemoteWorkTogether API", "status": "online", "users": session_manager.get_all_users().__len__()}


@app.get("/api/rooms")
async def get_rooms():
    return {"rooms": room_manager.get_rooms_as_dict()}


@app.get("/api/users")
async def get_users():
    return {"users": session_manager.get_users_as_dict()}


@app.get("/api/health")
async def health():
    return {
        "status": "healthy",
        "connected_users": connection_manager.get_user_count(),
        "rooms": len(room_manager.rooms),
        "timestamp": time.time(),
    }


@app.api_route("/api/join", methods=["GET", "POST"])
async def join(username: str = Query(...), avatar: str = Query("astronaut")):
    """Create a user session and return credentials."""
    if not username or len(username.strip()) < 1 or len(username) > 30:
        raise HTTPException(status_code=400, detail="Invalid username")
    user = session_manager.create_user(username.strip(), avatar)
    return {"user": user.model_dump()}


# ──────────────────────────────────────────────────────────────────────────────
# WebSocket Handler
# ──────────────────────────────────────────────────────────────────────────────

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    user = session_manager.get_user(user_id)
    if not user:
        await websocket.close(code=4001, reason="User not found. Please join first.")
        return

    await connection_manager.connect(websocket, user_id)
    room_manager.add_member("lobby", user_id)
    session_manager.update_user_room(user_id, "lobby")

    # Announce join to lobby
    await connection_manager.broadcast_to_all({
        "type": MessageType.USER_JOIN,
        "payload": {
            "user": user.model_dump(),
            "room_id": "lobby",
        },
        "timestamp": time.time(),
    })

    # Send initial state to the new user
    await connection_manager.send_personal(user_id, {
        "type": MessageType.USER_LIST,
        "payload": {
            "users": session_manager.get_users_as_dict(),
            "rooms": room_manager.get_rooms_as_dict(),
            "your_id": user_id,
        },
        "timestamp": time.time(),
    })

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type")
            payload = msg.get("payload", {})

            await handle_message(user_id, msg_type, payload)

    except WebSocketDisconnect:
        await handle_disconnect(user_id)
    except Exception as e:
        logger.error(f"WebSocket error for {user_id}: {e}")
        await handle_disconnect(user_id)


async def handle_message(user_id: str, msg_type: str, payload: dict):
    user = session_manager.get_user(user_id)
    if not user:
        return

    # ── Chat Message ──────────────────────────────────────────────────────────
    if msg_type == MessageType.CHAT_MESSAGE:
        room_id = payload.get("room_id", user.room_id)
        message = {
            "type": MessageType.CHAT_MESSAGE,
            "payload": {
                "id": str(uuid.uuid4())[:8],
                "sender_id": user_id,
                "username": user.username,
                "content": payload.get("content", ""),
                "room_id": room_id,
                "avatar": user.avatar,
                "color": user.color,
                "timestamp": time.time(),
                "message_type": payload.get("message_type", "text"),
            },
            "timestamp": time.time(),
        }
        await connection_manager.broadcast_to_room(room_id, message)

    # ── Reaction ──────────────────────────────────────────────────────────────
    elif msg_type == MessageType.REACTION:
        room_id = payload.get("room_id", user.room_id)
        reaction = reaction_handler.create_reaction_payload(
            sender_id=user_id,
            username=user.username,
            content=payload.get("content", "👍"),
            room_id=room_id,
            reaction_type=payload.get("reaction_type", "emoji"),
            x=payload.get("x"),
            y=payload.get("y"),
        )
        await connection_manager.broadcast_to_room(room_id, {
            "type": MessageType.REACTION,
            "payload": reaction,
            "timestamp": time.time(),
        })

    # ── Room Create ───────────────────────────────────────────────────────────
    elif msg_type == MessageType.ROOM_CREATE:
        name = payload.get("name", f"{user.username}'s Cabin")
        emoji = payload.get("emoji", "🚪")
        description = payload.get("description", "")
        is_private = payload.get("is_private", True)

        room = room_manager.create_room(
            name=name,
            created_by=user_id,
            is_private=is_private,
            description=description,
            emoji=emoji,
        )
        connection_manager.add_room(room.id)

        # ── Immediately move creator into the new room ──────────────────────
        old_room = user.room_id
        room_manager.remove_member(old_room, user_id)
        connection_manager.move_user_to_room(user_id, old_room, room.id)
        room_manager.add_member(room.id, user_id)
        session_manager.update_user_room(user_id, room.id)

        # Notify everyone in the old room that creator left
        await connection_manager.broadcast_to_room(old_room, {
            "type": MessageType.ROOM_LEAVE,
            "payload": {"user_id": user_id, "username": user.username, "room_id": old_room},
            "timestamp": time.time(),
        })

        # Broadcast updated room list to everyone (includes new room)
        await connection_manager.broadcast_to_all({
            "type": MessageType.ROOM_UPDATE,
            "payload": {"rooms": room_manager.get_rooms_as_dict()},
            "timestamp": time.time(),
        })

        # Tell creators client about the new room and that they moved into it
        await connection_manager.send_personal(user_id, {
            "type": MessageType.USER_LIST,
            "payload": {
                "users": session_manager.get_users_as_dict(),
                "rooms": room_manager.get_rooms_as_dict(),
                "current_room_users": session_manager.get_users_as_dict(room.id),
                "your_id": user_id,
                "moved_to": room.id,
            },
            "timestamp": time.time(),
        })

    # ── Room Join ─────────────────────────────────────────────────────────────
    elif msg_type == MessageType.ROOM_JOIN:
        target_room_id = payload.get("room_id")
        if not target_room_id or not room_manager.room_exists(target_room_id):
            await connection_manager.send_personal(user_id, {
                "type": MessageType.ERROR,
                "payload": {"message": "Room not found"},
            })
            return

        if not room_manager.can_join(target_room_id, user_id):
            await connection_manager.send_personal(user_id, {
                "type": MessageType.ERROR,
                "payload": {"message": "Cannot join this room (full or private)"},
            })
            return

        old_room = user.room_id
        room_manager.remove_member(old_room, user_id)
        connection_manager.move_user_to_room(user_id, old_room, target_room_id)
        room_manager.add_member(target_room_id, user_id)
        session_manager.update_user_room(user_id, target_room_id)

        room = room_manager.get_room(target_room_id)

        # Notify everyone in old room
        await connection_manager.broadcast_to_room(old_room, {
            "type": MessageType.ROOM_LEAVE,
            "payload": {"user_id": user_id, "username": user.username, "room_id": old_room},
            "timestamp": time.time(),
        })

        # Notify everyone in new room
        await connection_manager.broadcast_to_room(target_room_id, {
            "type": MessageType.ROOM_JOIN,
            "payload": {
                "user": user.model_dump(),
                "room_id": target_room_id,
                "room_name": room.name if room else "",
            },
            "timestamp": time.time(),
        })

        # Send user the room members
        room_users = session_manager.get_users_as_dict(target_room_id)
        await connection_manager.send_personal(user_id, {
            "type": MessageType.USER_LIST,
            "payload": {
                "users": session_manager.get_users_as_dict(),
                "rooms": room_manager.get_rooms_as_dict(),
                "current_room_users": room_users,
                "your_id": user_id,
                "moved_to": target_room_id,
            },
            "timestamp": time.time(),
        })

        # Broadcast updated rooms + user info to everyone so sidebar stays in sync
        await connection_manager.broadcast_to_all({
            "type": MessageType.ROOM_UPDATE,
            "payload": {"rooms": room_manager.get_rooms_as_dict()},
            "timestamp": time.time(),
        })
        # Broadcast the user's updated room_id to everyone
        await connection_manager.broadcast_to_all({
            "type": MessageType.USER_JOIN,
            "payload": {"user": user.model_dump(), "room_id": target_room_id},
            "timestamp": time.time(),
        })


    # ── Room Invite ───────────────────────────────────────────────────────────
    elif msg_type == MessageType.ROOM_INVITE:
        target_user_id = payload.get("target_user_id")
        room_id = payload.get("room_id", user.room_id)
        room = room_manager.get_room(room_id)

        if target_user_id and room:
            # Add to allowed members for private rooms
            room_manager.add_member(room_id, target_user_id)
            await connection_manager.send_personal(target_user_id, {
                "type": MessageType.ROOM_INVITE,
                "payload": {
                    "room": room.model_dump(),
                    "from_user": user.username,
                    "from_id": user_id,
                },
                "timestamp": time.time(),
            })

    # ── WebRTC Signaling ──────────────────────────────────────────────────────
    elif msg_type in [MessageType.WEBRTC_OFFER, MessageType.WEBRTC_ANSWER, MessageType.WEBRTC_ICE]:
        target_id = payload.get("target_id")
        if target_id:
            await connection_manager.send_personal(target_id, {
                "type": msg_type,
                "payload": payload,
                "sender_id": user_id,
                "timestamp": time.time(),
            })

    # ── Status Update ─────────────────────────────────────────────────────────
    elif msg_type == MessageType.STATUS_UPDATE:
        new_status = payload.get("status", "online")
        session_manager.update_user_status(user_id, new_status)
        await connection_manager.broadcast_to_all({
            "type": MessageType.STATUS_UPDATE,
            "payload": {"user_id": user_id, "status": new_status},
            "timestamp": time.time(),
        })

    # ── Ping / Pong ───────────────────────────────────────────────────────────
    elif msg_type == MessageType.PING:
        await connection_manager.send_personal(user_id, {
            "type": MessageType.PONG,
            "payload": {"timestamp": time.time()},
        })


async def handle_disconnect(user_id: str):
    user = session_manager.get_user(user_id)
    if user:
        room_id = user.room_id
        room_manager.remove_member(room_id, user_id)

        # If the room was deleted (creator left empty private room), clean up connection_manager too
        if not room_manager.room_exists(room_id) and room_id != "lobby":
            connection_manager.remove_room(room_id)

        connection_manager.disconnect(user_id)
        session_manager.remove_user(user_id)

        await connection_manager.broadcast_to_all({
            "type": MessageType.USER_LEAVE,
            "payload": {
                "user_id": user_id,
                "username": user.username,
                "room_id": room_id,
            },
            "timestamp": time.time(),
        })

        # Broadcast updated rooms so clients remove deleted cabins from sidebar
        await connection_manager.broadcast_to_all({
            "type": MessageType.ROOM_UPDATE,
            "payload": {"rooms": room_manager.get_rooms_as_dict()},
            "timestamp": time.time(),
        })
        logger.info(f"User {user.username} ({user_id}) disconnected")



# ──────────────────────────────────────────────────────────────────────────────
# Entry Point
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host=host, port=port, reload=True, log_level="info")
