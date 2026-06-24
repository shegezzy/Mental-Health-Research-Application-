"""
Simple in-memory session store for chat sessions.
In production, replace with Redis or a DB-backed store.
"""
import uuid
from typing import Dict, List, Optional
from datetime import datetime, timedelta

# session_id → {created_at, history, turn_count}
_store: Dict[str, dict] = {}

SESSION_TTL_MINUTES = 60


def create_session() -> str:
    session_id = str(uuid.uuid4())
    _store[session_id] = {
        "created_at": datetime.utcnow(),
        "history": [],
        "turn_count": 0,
    }
    _cleanup_expired()
    return session_id


def get_session(session_id: str) -> Optional[dict]:
    session = _store.get(session_id)
    if not session:
        return None
    if datetime.utcnow() - session["created_at"] > timedelta(minutes=SESSION_TTL_MINUTES):
        del _store[session_id]
        return None
    return session


def add_turn(session_id: str, user_msg: str, ai_reply: str) -> int:
    session = get_session(session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found or expired")
    session["history"].append({"role": "user", "content": user_msg})
    session["history"].append({"role": "assistant", "content": ai_reply})
    session["turn_count"] += 1
    return session["turn_count"]


def get_history(session_id: str) -> List[Dict]:
    session = get_session(session_id)
    return session["history"] if session else []


def get_turn_count(session_id: str) -> int:
    session = get_session(session_id)
    return session["turn_count"] if session else 0


def _cleanup_expired():
    cutoff = datetime.utcnow() - timedelta(minutes=SESSION_TTL_MINUTES)
    expired = [k for k, v in _store.items() if v["created_at"] < cutoff]
    for k in expired:
        del _store[k]
