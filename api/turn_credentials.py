"""
Dynamic TURN credential endpoint.

Uses HMAC-SHA1 time-limited credentials (RFC 5766 style) so:
  - No passwords are stored or hardcoded in the frontend
  - Credentials auto-expire after TTL_SECONDS
  - Anyone without your backend can't abuse your TURN server
"""

import os
import time
import hmac
import hashlib
import base64

from fastapi import APIRouter

router = APIRouter()

# Must match the TURN_SECRET set in your Fly.io app secrets
TURN_SECRET = os.getenv("TURN_SECRET", "changeme_set_in_env")
TURN_HOST   = os.getenv("TURN_HOST", "remotework-turn.fly.dev")
TTL_SECONDS = 3600  # Credentials valid for 1 hour


def _generate_credential(username: str) -> str:
    """Generate HMAC-SHA1 credential for a time-limited username."""
    key = TURN_SECRET.encode("utf-8")
    msg = username.encode("utf-8")
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    return base64.b64encode(digest).decode("utf-8")


@router.get("/api/turn-credentials")
async def get_turn_credentials():
    """
    Returns short-lived TURN credentials for the frontend to use.
    Frontend calls this once on connect, gets time-limited creds valid for 1h.
    """
    expiry = int(time.time()) + TTL_SECONDS
    username = f"{expiry}:remoteworktogether"
    credential = _generate_credential(username)

    return {
        "ttl": TTL_SECONDS,
        "iceServers": [
            # STUN servers (free, no auth needed)
            {"urls": "stun:stun.l.google.com:19302"},
            {"urls": "stun:stun1.l.google.com:19302"},
            {"urls": "stun:stun.cloudflare.com:3478"},
            # Your self-hosted TURN server
            {
                "urls": [
                    f"turn:{TURN_HOST}:3478",
                    f"turn:{TURN_HOST}:3478?transport=tcp",
                ],
                "username": username,
                "credential": credential,
            },
        ],
    }
