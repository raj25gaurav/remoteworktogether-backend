"""
Database layer using Supabase (free PostgreSQL).
All persistent data goes here: users, sessions, feedback, friend suggestions.
"""
import os
import time
import hashlib
import secrets
from typing import Optional, List, Dict, Any
from supabase import create_client, Client

_supabase: Optional[Client] = None


def get_db() -> Client:
    global _supabase
    if _supabase is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_ANON_KEY")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY must be set")
        _supabase = create_client(url, key)
    return _supabase


# ── Password helpers ──────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """SHA-256 hash with a fixed salt prefix. Good enough for an MVP."""
    salt = os.getenv("PW_SALT", "rwt-salt-2025")
    return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()


def verify_password(plain: str, hashed: str) -> bool:
    return hash_password(plain) == hashed


# ── Users ─────────────────────────────────────────────────────────────────────

def db_get_user_by_username(username: str) -> Optional[Dict]:
    try:
        res = get_db().table("rwt_users").select("*").eq("username", username.lower()).limit(1).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        print(f"[DB] get_user_by_username error: {e}")
        return None


def db_get_user_by_id(user_id: str) -> Optional[Dict]:
    try:
        res = get_db().table("rwt_users").select("*").eq("id", user_id).limit(1).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        print(f"[DB] get_user_by_id error: {e}")
        return None


def db_create_user(
    username: str,
    password: str,
    display_name: str,
    avatar: str,
    profession: str,
    bio: str,
    interests: List[str],
) -> Optional[Dict]:
    try:
        db = get_db()
        user_id = secrets.token_hex(12)
        row = {
            "id": user_id,
            "username": username.lower(),
            "password_hash": hash_password(password),
            "display_name": display_name,
            "avatar": avatar,
            "profession": profession,
            "bio": bio,
            "interests": interests,
            "created_at": time.time(),
            "last_seen": time.time(),
            "total_lobby_seconds": 0,
            "total_cabin_seconds": 0,
        }
        res = db.table("rwt_users").insert(row).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        print(f"[DB] create_user error: {e}")
        return None


def db_update_last_seen(user_id: str):
    try:
        get_db().table("rwt_users").update({"last_seen": time.time()}).eq("id", user_id).execute()
    except Exception as e:
        print(f"[DB] update_last_seen error: {e}")


def db_get_all_users(exclude_id: str = None) -> List[Dict]:
    try:
        q = get_db().table("rwt_users").select(
            "id, username, display_name, avatar, profession, interests, bio, last_seen, total_lobby_seconds, total_cabin_seconds"
        )
        if exclude_id:
            q = q.neq("id", exclude_id)
        res = q.order("last_seen", desc=True).execute()
        return res.data or []
    except Exception as e:
        print(f"[DB] get_all_users error: {e}")
        return []


# ── Session time tracking ─────────────────────────────────────────────────────

def db_start_session(user_id: str, location_type: str, room_name: str = "lobby") -> Optional[str]:
    """Returns session_id to be stored in memory for later end."""
    try:
        session_id = secrets.token_hex(8)
        get_db().table("rwt_sessions").insert({
            "id": session_id,
            "user_id": user_id,
            "location_type": location_type,
            "room_name": room_name,
            "start_time": time.time(),
            "end_time": None,
            "duration_seconds": 0,
        }).execute()
        return session_id
    except Exception as e:
        print(f"[DB] start_session error: {e}")
        return None


def db_end_session(session_id: str, user_id: str, location_type: str):
    """Ends a session and updates cumulative time on the user row."""
    try:
        db = get_db()
        # Get session start time
        res = db.table("rwt_sessions").select("start_time").eq("id", session_id).limit(1).execute()
        if not res.data:
            return
        start = res.data[0]["start_time"]
        duration = max(0, int(time.time() - start))

        # Update session row
        db.table("rwt_sessions").update({
            "end_time": time.time(),
            "duration_seconds": duration,
        }).eq("id", session_id).execute()

        # Increment cumulative time on user
        user = db_get_user_by_id(user_id)
        if user:
            field = "total_lobby_seconds" if location_type == "lobby" else "total_cabin_seconds"
            new_val = (user.get(field) or 0) + duration
            db.table("rwt_users").update({field: new_val}).eq("id", user_id).execute()
    except Exception as e:
        print(f"[DB] end_session error: {e}")


def db_get_time_stats(user_id: str) -> Dict:
    try:
        user = db_get_user_by_id(user_id)
        if not user:
            return {}
        return {
            "total_lobby_seconds": user.get("total_lobby_seconds", 0),
            "total_cabin_seconds": user.get("total_cabin_seconds", 0),
        }
    except Exception as e:
        print(f"[DB] get_time_stats error: {e}")
        return {}


# ── Feedback ──────────────────────────────────────────────────────────────────

def db_save_feedback(user_id: Optional[str], rating: int, liked: str, improve: str):
    try:
        get_db().table("rwt_feedback").insert({
            "user_id": user_id,
            "rating": rating,
            "liked": liked,
            "improve": improve,
            "created_at": time.time(),
        }).execute()
    except Exception as e:
        print(f"[DB] save_feedback error: {e}")


# ── Friend Suggestions (similarity score) ────────────────────────────────────

def _similarity_score(me: Dict, other: Dict) -> int:
    score = 0
    # Same profession
    if me.get("profession") and me["profession"].lower() == (other.get("profession") or "").lower():
        score += 40
    # Shared interests
    my_interests = set(i.lower() for i in (me.get("interests") or []))
    their_interests = set(i.lower() for i in (other.get("interests") or []))
    shared = my_interests & their_interests
    score += min(45, len(shared) * 15)
    # Both active (seen in last hour)
    if other.get("last_seen") and time.time() - other["last_seen"] < 3600:
        score += 5
    # Similar time spent (both prefer lobbing vs cabins)
    my_lobby = me.get("total_lobby_seconds", 0)
    my_cabin = me.get("total_cabin_seconds", 0)
    t_lobby = other.get("total_lobby_seconds", 0)
    t_cabin = other.get("total_cabin_seconds", 0)
    if (my_lobby > my_cabin) == (t_lobby > t_cabin):
        score += 10
    return min(100, score)


def db_get_friend_suggestions(user_id: str, online_user_ids: List[str]) -> List[Dict]:
    """Returns all users with similarity score + online status, sorted by score."""
    try:
        me = db_get_user_by_id(user_id)
        if not me:
            return []
        others = db_get_all_users(exclude_id=user_id)
        results = []
        for u in others:
            score = _similarity_score(me, u)
            is_online = u["id"] in online_user_ids
            results.append({
                "id": u["id"],
                "username": u["username"],
                "display_name": u["display_name"],
                "avatar": u["avatar"],
                "profession": u["profession"],
                "interests": u["interests"],
                "similarity": score,
                "is_online": is_online,
                "last_seen": u.get("last_seen"),
                "total_lobby_seconds": u.get("total_lobby_seconds", 0),
                "total_cabin_seconds": u.get("total_cabin_seconds", 0),
            })
        # Sort: online first, then by similarity score
        results.sort(key=lambda x: (not x["is_online"], -x["similarity"]))
        return results
    except Exception as e:
        print(f"[DB] get_friend_suggestions error: {e}")
        return []


# ── Friend Requests ───────────────────────────────────────────────────────────

def db_send_friend_request(from_id: str, to_id: str) -> Dict:
    """Send a friend request. Returns error if already sent/friends."""
    try:
        db = get_db()
        # Two separate queries to avoid complex PostgREST OR
        r1 = db.table("rwt_friend_requests").select("status").eq("from_id", from_id).eq("to_id", to_id).limit(1).execute()
        r2 = db.table("rwt_friend_requests").select("status").eq("from_id", to_id).eq("to_id", from_id).limit(1).execute()
        existing = (r1.data or []) + (r2.data or [])
        if existing:
            status = existing[0]["status"]
            if status == "accepted":
                return {"ok": False, "detail": "You are already friends!"}
            if status == "pending":
                return {"ok": False, "detail": "Friend request already sent!"}
            # If rejected, allow re-sending by updating status back to pending
            db.table("rwt_friend_requests").update({"status": "pending", "created_at": time.time()}).eq("from_id", from_id).eq("to_id", to_id).execute()
            return {"ok": True}
        req_id = secrets.token_hex(8)
        db.table("rwt_friend_requests").insert({
            "id": req_id,
            "from_id": from_id,
            "to_id": to_id,
            "status": "pending",
            "created_at": time.time(),
        }).execute()
        return {"ok": True, "request_id": req_id}
    except Exception as e:
        print(f"[DB] send_friend_request error: {e}")
        return {"ok": False, "detail": str(e)}


def db_respond_friend_request(request_id: str, responder_id: str, accept: bool) -> Dict:
    """Accept or reject a pending friend request."""
    try:
        db = get_db()
        res = db.table("rwt_friend_requests").select("*").eq("id", request_id).limit(1).execute()
        if not res.data:
            return {"ok": False, "detail": "Request not found"}
        req = res.data[0]
        if req["to_id"] != responder_id:
            return {"ok": False, "detail": "Not authorized"}
        new_status = "accepted" if accept else "rejected"
        db.table("rwt_friend_requests").update({"status": new_status}).eq("id", request_id).execute()
        # Return from_id so frontend knows who to update
        return {"ok": True, "status": new_status, "from_id": req["from_id"], "to_id": req["to_id"]}
    except Exception as e:
        print(f"[DB] respond_friend_request error: {e}")
        return {"ok": False, "detail": str(e)}


def db_get_pending_requests(user_id: str) -> List[Dict]:
    """Get pending incoming friend requests, enriched with sender info."""
    try:
        db = get_db()
        res = db.table("rwt_friend_requests").select("*").eq("to_id", user_id).eq("status", "pending").execute()
        enriched = []
        for row in (res.data or []):
            sender = db_get_user_by_id(row["from_id"])
            enriched.append({
                **row,
                "sender_display_name": sender["display_name"] if sender else "Unknown",
                "sender_avatar": sender["avatar"] if sender else "astronaut",
                "sender_profession": sender.get("profession", "") if sender else "",
            })
        return enriched
    except Exception as e:
        print(f"[DB] get_pending_requests error: {e}")
        return []


def db_get_friends(user_id: str, online_user_ids: List[str]) -> List[Dict]:
    """Get all accepted friends (two-direction) with online status."""
    try:
        db = get_db()
        sent = db.table("rwt_friend_requests").select("to_id").eq("from_id", user_id).eq("status", "accepted").execute()
        recv = db.table("rwt_friend_requests").select("from_id").eq("to_id", user_id).eq("status", "accepted").execute()
        friend_ids = [r["to_id"] for r in (sent.data or [])] + [r["from_id"] for r in (recv.data or [])]
        if not friend_ids:
            return []
        friends = []
        for fid in friend_ids:
            u = db_get_user_by_id(fid)
            if u:
                friends.append({
                    "id": u["id"],
                    "username": u["username"],
                    "display_name": u["display_name"],
                    "avatar": u["avatar"],
                    "profession": u.get("profession", ""),
                    "is_online": u["id"] in online_user_ids,
                    "last_seen": u.get("last_seen"),
                })
        friends.sort(key=lambda x: not x["is_online"])
        return friends
    except Exception as e:
        print(f"[DB] get_friends error: {e}")
        return []


def db_get_request_status(from_id: str, to_id: str) -> str:
    """Returns 'none' | 'pending' | 'accepted' | 'rejected'."""
    try:
        db = get_db()
        r1 = db.table("rwt_friend_requests").select("status").eq("from_id", from_id).eq("to_id", to_id).limit(1).execute()
        if r1.data:
            return r1.data[0]["status"]
        r2 = db.table("rwt_friend_requests").select("status").eq("from_id", to_id).eq("to_id", from_id).limit(1).execute()
        if r2.data:
            return r2.data[0]["status"]
        return "none"
    except Exception as e:
        print(f"[DB] get_request_status error: {e}")
        return "none"


# ── Direct Messages ───────────────────────────────────────────────────────────

def db_save_dm(from_id: str, to_id: str, content: str) -> Optional[Dict]:
    """Save a direct message between two users."""
    try:
        row = {
            "id": secrets.token_hex(10),
            "from_id": from_id,
            "to_id": to_id,
            "content": content,
            "created_at": time.time(),
            "is_read": False,
        }
        res = get_db().table("rwt_direct_messages").insert(row).execute()
        return res.data[0] if res.data else row
    except Exception as e:
        print(f"[DB] save_dm error: {e}")
        return None


def db_get_dm_history(user_a: str, user_b: str, limit: int = 60) -> List[Dict]:
    """Get message history between two users, sorted oldest first."""
    try:
        db = get_db()
        r1 = db.table("rwt_direct_messages").select("*").eq("from_id", user_a).eq("to_id", user_b).order("created_at").limit(limit).execute()
        r2 = db.table("rwt_direct_messages").select("*").eq("from_id", user_b).eq("to_id", user_a).order("created_at").limit(limit).execute()
        combined = (r1.data or []) + (r2.data or [])
        combined.sort(key=lambda x: x.get("created_at", 0))
        return combined[-limit:]
    except Exception as e:
        print(f"[DB] get_dm_history error: {e}")
        return []


def db_mark_dms_read(from_id: str, to_id: str):
    """Mark all unread messages from `from_id` to `to_id` as read."""
    try:
        get_db().table("rwt_direct_messages").update({"is_read": True}).eq("from_id", from_id).eq("to_id", to_id).eq("is_read", False).execute()
    except Exception as e:
        print(f"[DB] mark_dms_read error: {e}")


def db_get_unread_counts(user_id: str) -> Dict[str, int]:
    """Number of unread DMs per sender for a given user."""
    try:
        res = get_db().table("rwt_direct_messages").select("from_id").eq("to_id", user_id).eq("is_read", False).execute()
        counts: Dict[str, int] = {}
        for row in (res.data or []):
            fid = row["from_id"]
            counts[fid] = counts.get(fid, 0) + 1
        return counts
    except Exception as e:
        print(f"[DB] get_unread_counts error: {e}")
        return {}
