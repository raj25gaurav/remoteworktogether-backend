"""
Auth + User + Feedback + Friends API endpoints.
All persistent, user-facing data routes.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from core.database import (
    db_create_user, db_get_user_by_username, db_get_user_by_id,
    verify_password, db_update_last_seen,
    db_save_feedback, db_get_friend_suggestions,
    db_get_time_stats, db_start_session, db_end_session,
    db_get_all_users,
)

router = APIRouter(prefix="/api", tags=["auth"])

# ── Schemas ───────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str
    password: str
    display_name: str
    avatar: str = "astronaut"
    profession: str = ""
    bio: str = ""
    interests: List[str] = []

class LoginRequest(BaseModel):
    username: str
    password: str

class FeedbackRequest(BaseModel):
    user_id: Optional[str] = None
    rating: int          # 1–5
    liked: str = ""
    improve: str = ""

class SessionStartRequest(BaseModel):
    user_id: str
    location_type: str   # "lobby" | "cabin"
    room_name: str = "lobby"

class SessionEndRequest(BaseModel):
    session_id: str
    user_id: str
    location_type: str

# ── Auth ──────────────────────────────────────────────────────────────────────

@router.post("/auth/register")
async def register(req: RegisterRequest):
    username = req.username.strip().lower()
    if len(username) < 2 or len(username) > 30:
        raise HTTPException(400, "Username must be 2-30 characters")
    if len(req.password) < 4:
        raise HTTPException(400, "Password must be at least 4 characters")
    # Check username taken
    existing = db_get_user_by_username(username)
    if existing:
        raise HTTPException(409, "Username already taken. Try a different one!")
    user = db_create_user(
        username=username,
        password=req.password,
        display_name=req.display_name or req.username,
        avatar=req.avatar,
        profession=req.profession,
        bio=req.bio,
        interests=req.interests,
    )
    if not user:
        raise HTTPException(500, "Could not create account. Please try again.")
    return {
        "ok": True,
        "user": _safe_user(user),
    }


@router.post("/auth/login")
async def login(req: LoginRequest):
    user = db_get_user_by_username(req.username.strip().lower())
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(401, "Wrong username or password")
    db_update_last_seen(user["id"])
    return {
        "ok": True,
        "user": _safe_user(user),
    }


@router.get("/auth/profile/{user_id}")
async def get_profile(user_id: str):
    user = db_get_user_by_id(user_id)
    if not user:
        raise HTTPException(404, "User not found")
    return {"user": _safe_user(user)}

# ── Feedback ──────────────────────────────────────────────────────────────────

@router.post("/feedback")
async def submit_feedback(req: FeedbackRequest):
    if not 1 <= req.rating <= 5:
        raise HTTPException(400, "Rating must be 1-5")
    db_save_feedback(req.user_id, req.rating, req.liked, req.improve)
    return {"ok": True, "message": "Thanks for your feedback! 🙌"}

# ── Session Time Tracking ─────────────────────────────────────────────────────

@router.post("/session/start")
async def start_session(req: SessionStartRequest):
    session_id = db_start_session(req.user_id, req.location_type, req.room_name)
    return {"ok": True, "session_id": session_id}

@router.post("/session/end")
async def end_session(req: SessionEndRequest):
    db_end_session(req.session_id, req.user_id, req.location_type)
    stats = db_get_time_stats(req.user_id)
    return {"ok": True, "stats": stats}

@router.get("/session/stats/{user_id}")
async def get_stats(user_id: str):
    stats = db_get_time_stats(user_id)
    return {"stats": stats}

# ── Friends & Suggestions ─────────────────────────────────────────────────────

@router.get("/friends/suggest/{user_id}")
async def suggest_friends(user_id: str, online_ids: str = ""):
    """online_ids is comma-separated list of currently connected user IDs"""
    online_list = [x for x in online_ids.split(",") if x]
    suggestions = db_get_friend_suggestions(user_id, online_list)
    return {"suggestions": suggestions}

@router.get("/friends/all")
async def all_users(online_ids: str = ""):
    """Return all registered users with online status (no exclude)."""
    online_list = [x for x in online_ids.split(",") if x]
    users = db_get_all_users()
    result = []
    for u in users:
        result.append({
            "id": u["id"],
            "username": u["username"],
            "display_name": u["display_name"],
            "avatar": u["avatar"],
            "profession": u.get("profession", ""),
            "is_online": u["id"] in online_list,
            "last_seen": u.get("last_seen"),
        })
    return {"users": result}


# ── Helper ────────────────────────────────────────────────────────────────────

def _safe_user(u: dict) -> dict:
    """Strip password_hash before sending to frontend."""
    return {k: v for k, v in u.items() if k != "password_hash"}
