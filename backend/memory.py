"""In-process session memory store for TailorTalk.

Each chat session gets its own ``ConversationBufferMemory`` instance keyed
by ``session_id``. Memory lives only for the lifetime of the process and
is reclaimed by ``cleanup_old_sessions`` after one hour of inactivity.
"""

import time
from typing import Dict, List, TypedDict

from langchain.memory import ConversationBufferMemory

SESSION_TTL_SECONDS = 60 * 60  # 1 hour
MEMORY_KEY = "chat_history"
RECENT_SEARCHES_MAX = 5


class _SessionEntry(TypedDict):
    memory: ConversationBufferMemory
    created_at: float
    recent_searches: List[str]


_sessions: Dict[str, _SessionEntry] = {}


def _new_entry() -> _SessionEntry:
    return {
        "memory": ConversationBufferMemory(
            memory_key=MEMORY_KEY,
            return_messages=True,
        ),
        "created_at": time.time(),
        "recent_searches": [],
    }


def get_memory(session_id: str) -> ConversationBufferMemory:
    """Return the memory for ``session_id``, creating it if needed.

    The returned ``ConversationBufferMemory`` uses ``chat_history`` as its
    memory key and returns messages (not strings) so it can plug directly
    into a chat-style prompt.
    """
    entry = _sessions.get(session_id)
    if entry is None:
        entry = _new_entry()
        _sessions[session_id] = entry
    return entry["memory"]


def clear_memory(session_id: str) -> None:
    """Clear stored messages and recent searches for ``session_id``.

    The session entry stays in the store with its original creation time;
    callers can keep using ``get_memory(session_id)`` afterward and will
    get the same (now-empty) memory instance.
    """
    entry = _sessions.get(session_id)
    if entry is not None:
        entry["memory"].clear()
        entry["recent_searches"] = []


def add_recent_search(session_id: str, query: str) -> None:
    """Record ``query`` as the most recent search for the session.

    The list is deduplicated (newest occurrence wins) and capped at the
    five most recent entries. Empty/whitespace queries are ignored. If
    the session does not yet exist, it is created.
    """
    if not query or not query.strip():
        return
    entry = _sessions.get(session_id)
    if entry is None:
        entry = _new_entry()
        _sessions[session_id] = entry
    q = query.strip()
    existing = [r for r in entry["recent_searches"] if r != q]
    entry["recent_searches"] = ([q] + existing)[:RECENT_SEARCHES_MAX]


def get_recent_searches(session_id: str) -> List[str]:
    """Return the up-to-5 most recent unique queries for the session."""
    entry = _sessions.get(session_id)
    if entry is None:
        return []
    return list(entry["recent_searches"])


def cleanup_old_sessions() -> int:
    """Drop sessions older than ``SESSION_TTL_SECONDS`` (1 hour).

    Returns:
        The number of sessions removed.
    """
    now = time.time()
    expired = [
        sid
        for sid, entry in _sessions.items()
        if now - entry["created_at"] > SESSION_TTL_SECONDS
    ]
    for sid in expired:
        del _sessions[sid]
    return len(expired)
