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
    db_send_friend_request, db_respond_friend_request,
    db_get_pending_requests, db_get_friends, db_get_request_status,
    db_save_dm, db_get_dm_history, db_mark_dms_read, db_get_unread_counts,
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

class RegisterCandidateReq(BaseModel):
    username: str
    password: str
    full_name: str
    current_org: str
    has_referral: bool = False
    skills: List[str] = []
    experience_years: int = 0
    expected_salary: int = 0
    bio: str = ""

class RegisterOrganizationReq(BaseModel):
    username: str
    password: str
    company_name: str

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

class FriendRequestCreate(BaseModel):
    from_id: str
    to_id: str

class FriendRequestRespond(BaseModel):
    request_id: str
    responder_id: str
    accept: bool

class DMSendRequest(BaseModel):
    from_id: str
    to_id: str
    content: str

class DMMarkReadRequest(BaseModel):
    from_id: str   # the sender whose messages we are marking read
    to_id: str     # the current user (reader)

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

import json

@router.post("/auth/register/candidate")
async def register_candidate(req: RegisterCandidateReq):
    username = req.username.strip().lower()
    if len(username) < 2 or len(username) > 30:
        raise HTTPException(400, "Username must be 2-30 characters")
    if len(req.password) < 4:
        raise HTTPException(400, "Password must be at least 4 characters")
    
    existing = db_get_user_by_username(username)
    if existing:
        raise HTTPException(409, "Username already taken.")
        
    # We store the platform details in the bio/profession for now as an MVP
    bio_data = json.dumps({
        "full_name": req.full_name,
        "current_org": req.current_org,
        "has_referral": req.has_referral,
        "skills": req.skills,
        "experience_years": req.experience_years,
        "expected_salary": req.expected_salary,
        "bio": req.bio
    })
    
    user = db_create_user(
        username=username,
        password=req.password,
        display_name=req.full_name,
        avatar="astronaut",
        profession="candidate",
        bio=bio_data,
        interests=[],
    )
    if not user:
        raise HTTPException(500, "Could not create account.")
    return {"ok": True, "user": _safe_user(user)}

@router.post("/auth/register/organization")
async def register_organization(req: RegisterOrganizationReq):
    username = req.username.strip().lower()
    if len(username) < 2 or len(username) > 30:
        raise HTTPException(400, "Username must be 2-30 characters")
    if len(req.password) < 4:
        raise HTTPException(400, "Password must be at least 4 characters")
    
    existing = db_get_user_by_username(username)
    if existing:
        raise HTTPException(409, "Username already taken.")
        
    bio_data = json.dumps({"company_name": req.company_name})
    
    user = db_create_user(
        username=username,
        password=req.password,
        display_name=req.company_name,
        avatar="astronaut",
        profession="organization",
        bio=bio_data,
        interests=[],
    )
    if not user:
        raise HTTPException(500, "Could not create account.")
    return {"ok": True, "user": _safe_user(user)}

@router.get("/auth/stats")
async def get_stats():
    users = db_get_all_users()
    candidates = sum(1 for u in users if u.get("profession") == "candidate")
    orgs = sum(1 for u in users if u.get("profession") == "organization")
    return {"candidates": candidates, "companies": orgs}



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


# ── Friend Requests ───────────────────────────────────────────────────────────

@router.post("/friends/request")
async def send_friend_request(req: FriendRequestCreate):
    result = db_send_friend_request(req.from_id, req.to_id)
    # Don't throw 400 if it's "Already friends" or "Already sent"
    # The frontend catches `result.ok` anyway!
    if not result.get("ok") and "error" in result.get("detail", "").lower():
        raise HTTPException(400, result.get("detail", "Failed"))
    return result

@router.post("/friends/respond")
async def respond_friend_request(req: FriendRequestRespond):
    result = db_respond_friend_request(req.request_id, req.responder_id, req.accept)
    if not result.get("ok"):
        raise HTTPException(400, result.get("detail", "Failed"))
    return result

@router.get("/friends/pending/{user_id}")
async def get_pending(user_id: str):
    requests = db_get_pending_requests(user_id)
    return {"requests": requests}

@router.get("/friends/list/{user_id}")
async def get_friends(user_id: str, online_ids: str = ""):
    online_list = [x for x in online_ids.split(",") if x]
    friends = db_get_friends(user_id, online_list)
    return {"friends": friends}

@router.get("/friends/status")
async def get_friend_status(from_id: str, to_id: str):
    status = db_get_request_status(from_id, to_id)
    return {"status": status}


# ── Productivity Score (based on real session data) ───────────────────────────

@router.get("/score/{user_id}")
async def get_score(user_id: str):
    """Compute a productivity score (0-100) from session data."""
    import time as _time
    stats = db_get_time_stats(user_id)
    lobby = stats.get("total_lobby_seconds", 0) or 0
    cabin = stats.get("total_cabin_seconds", 0) or 0
    total = lobby + cabin
    # Scale: 1 hour = 20 pts, 2h = 40 pts ... max 100 at 5h
    time_score = min(60, int((total / 18000) * 60))
    # Bonus for cabin use (active collaboration)
    collab_bonus = min(20, int((cabin / max(1, total)) * 20))
    # Bonus for having profile filled (static)
    user = db_get_user_by_id(user_id)
    profile_bonus = 0
    if user:
        if user.get("interests"): profile_bonus += 10
        if user.get("bio"): profile_bonus += 5
        if user.get("profession"): profile_bonus += 5
    score = min(100, time_score + collab_bonus + profile_bonus)
    return {"score": max(5, score)}


# ── Direct Messages ───────────────────────────────────────────────────────────

@router.post("/dm/send")
async def send_dm(req: DMSendRequest):
    if not req.content.strip():
        raise HTTPException(400, "Message cannot be empty")
    if len(req.content) > 2000:
        raise HTTPException(400, "Message too long")
    msg = db_save_dm(req.from_id, req.to_id, req.content.strip())
    if not msg:
        raise HTTPException(500, "Failed to save message")
    return {"ok": True, "message": msg}

@router.get("/dm/history")
async def get_dm_history(user_a: str, user_b: str, limit: int = 60):
    messages = db_get_dm_history(user_a, user_b, limit)
    return {"messages": messages}

@router.post("/dm/read")
async def mark_read(req: DMMarkReadRequest):
    db_mark_dms_read(req.from_id, req.to_id)
    return {"ok": True}

@router.get("/dm/unread/{user_id}")
async def get_unread(user_id: str):
    counts = db_get_unread_counts(user_id)
    return {"unread": counts}


# ── Helper ────────────────────────────────────────────────────────────────────

def _safe_user(u: dict) -> dict:
    """Strip password_hash before sending to frontend."""
    return {k: v for k, v in u.items() if k != "password_hash"}
