"""Streamlit frontend for the TailorTalk Drive Agent (styled build).

Renders chat bubbles, file cards, empty states, and assistant extras as
custom HTML so the dark-theme stylesheet can lay them out exactly. All
clickable suggestion / recent-search / example controls route through a
single ``pending_message`` session-state flag that the chat input picks
up on the next rerun.
"""

import html
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")
REQUEST_TIMEOUT = 60

EXAMPLE_QUERIES = [
    "Find all PDFs modified this month",
    "Show spreadsheets with budget in the name",
    "Find documents containing project proposal",
    "What images were uploaded last week?",
]

TYPE_EMOJI: Dict[str, str] = {
    "PDF": "📄",
    "Google Doc": "📝",
    "Google Sheet": "📊",
    "Slides": "📑",
    "Image": "🖼️",
    "File": "📁",
}

TYPE_BADGE_CLASS: Dict[str, str] = {
    "PDF": "tt-badge-pdf",
    "Google Doc": "tt-badge-doc",
    "Google Sheet": "tt-badge-sheet",
    "Slides": "tt-badge-slides",
    "Image": "tt-badge-image",
    "File": "tt-badge-file",
}


# ---------------------------------------------------------------------------
# Page setup + CSS injection
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="TailorTalk Drive Agent",
    page_icon="🗂️",
    layout="wide",
)


def _load_css() -> None:
    """Inject styles.css into the page (one-shot per rerun)."""
    css_path = Path(__file__).parent / "styles.css"
    try:
        css = css_path.read_text(encoding="utf-8")
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        pass


_load_css()


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
def _init_state() -> None:
    """Initialize session_state keys on first run."""
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
    if "chat_history" not in st.session_state:
        st.session_state.chat_history: List[Dict[str, Any]] = []
    if "recent_searches" not in st.session_state:
        st.session_state.recent_searches: List[str] = []
    if "pending_message" not in st.session_state:
        st.session_state.pending_message = None
    if "error_banner" not in st.session_state:
        st.session_state.error_banner = None


_init_state()


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _esc(text: Any) -> str:
    """HTML-escape any value for safe injection."""
    return html.escape(str(text or ""))


def _esc_with_br(text: Any) -> str:
    """Escape and turn newlines into ``<br>`` so prose preserves line breaks."""
    return _esc(text).replace("\n", "<br>")


def _loading_message(query: str) -> str:
    """Pick a contextual spinner label based on keywords in the query."""
    q = (query or "").lower()
    if "pdf" in q:
        return "📄 Searching for PDFs..."
    if "image" in q or "photo" in q:
        return "🖼️ Looking for images..."
    if "sheet" in q or "spreadsheet" in q:
        return "📊 Finding spreadsheets..."
    if "last week" in q or "yesterday" in q or "this month" in q:
        return "📅 Filtering by date..."
    return "🔍 Searching your Drive..."


def _queue_message(text: str) -> None:
    """Queue a message to be auto-sent on the next rerun."""
    st.session_state.pending_message = text


# ---------------------------------------------------------------------------
# Backend calls
# ---------------------------------------------------------------------------
@st.cache_data(ttl=30, show_spinner=False)
def _fetch_health() -> Dict[str, Any]:
    """GET /health, cached for 30s so reruns don't hammer the backend."""
    try:
        r = requests.get(f"{BACKEND_URL}/health", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {
            "drive_connected": False,
            "status": "unreachable",
            "message": f"Backend unreachable: {e}",
        }


def _fetch_recent_searches(session_id: str) -> List[str]:
    """GET /recent-searches/{session_id}; return [] on any error."""
    try:
        r = requests.get(
            f"{BACKEND_URL}/recent-searches/{session_id}", timeout=10
        )
        r.raise_for_status()
        return r.json().get("queries", []) or []
    except Exception:
        return []


def _clear_session(session_id: str) -> bool:
    """DELETE /chat/{session_id}; return True on success."""
    try:
        r = requests.delete(f"{BACKEND_URL}/chat/{session_id}", timeout=10)
        r.raise_for_status()
        return True
    except Exception:
        return False


def _send_chat(message: str) -> Dict[str, Any]:
    """POST a chat turn and return the parsed response dict."""
    payload = {
        "message": message,
        "session_id": st.session_state.session_id,
        "chat_history": [
            {"role": m["role"], "content": m["content"]}
            for m in st.session_state.chat_history
        ],
    }
    r = requests.post(
        f"{BACKEND_URL}/chat", json=payload, timeout=REQUEST_TIMEOUT
    )
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# HTML renderers
# ---------------------------------------------------------------------------
def _render_user_bubble(content: str) -> None:
    """Render a right-aligned accent-colored user bubble."""
    st.markdown(
        f'<div class="tt-msg tt-msg-user">'
        f'  <div class="tt-bubble tt-bubble-user">{_esc_with_br(content)}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )


def _render_assistant_bubble(content: str) -> None:
    """Render a left-aligned dark-card assistant bubble."""
    st.markdown(
        f'<div class="tt-msg tt-msg-assistant">'
        f'  <div class="tt-bubble tt-bubble-assistant">{_esc_with_br(content)}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )


def _file_card_html(f: Dict[str, Any]) -> str:
    """Build the inner HTML for a single file card."""
    type_label = f.get("type_label") or "File"
    emoji = TYPE_EMOJI.get(type_label, "📁")
    badge_class = TYPE_BADGE_CLASS.get(type_label, "tt-badge-file")
    name = _esc(f.get("name") or "Untitled")
    modified = _esc(f.get("modified_time_formatted") or "")
    size = _esc(f.get("size_formatted") or "")
    preview = (f.get("preview_text") or "").strip()
    if len(preview) > 100:
        preview = preview[:100].rstrip() + "..."
    preview_html = (
        f'<div class="tt-file-preview">{_esc(preview)}</div>' if preview else ""
    )
    size_html = f'<span class="file-size">📦 {size}</span>' if size else ""
    meta_html = (
        f'<div class="tt-file-meta">{modified}</div>' if modified else ""
    )
    link = (f.get("web_view_link") or "").strip()
    open_btn = (
        f'<a class="tt-open-btn" href="{_esc(link)}" target="_blank" '
        f'rel="noopener noreferrer">Open in Drive →</a>'
        if link
        else ""
    )
    return (
        '<div class="tt-file-card">'
        f'  <div class="tt-file-icon">{emoji}</div>'
        '  <div class="tt-file-body">'
        f'    <div class="tt-file-name">{name}</div>'
        f'    <span class="tt-badge {badge_class}">{_esc(type_label)}</span>'
        f"    {size_html}"
        f"    {meta_html}"
        f"    {preview_html}"
        f"    {open_btn}"
        "  </div>"
        "</div>"
    )


def _render_files(files: List[Dict[str, Any]]) -> None:
    """Render a 2-column grid of file cards."""
    if not files:
        return
    cards = "".join(_file_card_html(f) for f in files)
    st.markdown(
        f'<div class="tt-files-grid">{cards}</div>',
        unsafe_allow_html=True,
    )


def _render_empty_state() -> None:
    """Decorative empty state when a search returned no files."""
    st.markdown(
        '<div class="tt-empty">'
        '  <div class="tt-empty-art">🔍 📭</div>'
        '  <div class="tt-empty-title">No files found for your search</div>'
        '  <div class="tt-empty-msg">Try one of the suggestions below.</div>'
        "</div>",
        unsafe_allow_html=True,
    )


def _render_suggestion_chips(suggestions: List[str], key_prefix: str) -> None:
    """Render the 2 follow-up suggestions as clickable chip buttons."""
    if not suggestions:
        return
    cols = st.columns(len(suggestions))
    for s_idx, sug in enumerate(suggestions):
        if cols[s_idx].button(sug, key=f"{key_prefix}_sug_{s_idx}"):
            _queue_message(sug)
            st.rerun()


def _render_assistant_extras(meta: Dict[str, Any], key_prefix: str) -> None:
    """Render search line, reasoning, files (or empty state), and chips."""
    query_used = (meta.get("query_used") or "").strip()
    reasoning = (meta.get("reasoning") or "").strip()
    files = meta.get("files") or []
    suggestions = meta.get("suggestions") or []
    search_performed = bool(meta.get("search_performed"))

    extras_lines: List[str] = []
    if query_used:
        extras_lines.append(
            f'<div class="tt-extras-line">🔍 Searched: '
            f"<code>{_esc(query_used)}</code></div>"
        )
    if reasoning:
        extras_lines.append(
            f'<div class="tt-extras-line">💡 {_esc(reasoning)}</div>'
        )
    if extras_lines:
        st.markdown(
            f'<div class="tt-extras">{"".join(extras_lines)}</div>',
            unsafe_allow_html=True,
        )

    if search_performed and files:
        _render_files(files)
        _render_suggestion_chips(suggestions, key_prefix=key_prefix)
    elif search_performed and not files:
        _render_empty_state()
        _render_suggestion_chips(suggestions, key_prefix=key_prefix)
    # Pure conversational reply (no search performed): no file section,
    # no suggestion chips — just the text response above.


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        '<div class="tt-sidebar-title">🗂️ TailorTalk</div>'
        '<div class="tt-sidebar-subtitle">Drive Agent</div>',
        unsafe_allow_html=True,
    )
    st.divider()

    st.markdown(
        '<div class="tt-sidebar-section">🔌 Drive Status</div>',
        unsafe_allow_html=True,
    )
    health = _fetch_health()
    if health.get("drive_connected"):
        st.markdown(
            '<div class="tt-status-row">'
            '<span class="tt-status-dot connected"></span>'
            '<span class="tt-status-label connected">● Connected</span>'
            "</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="tt-status-row">'
            '<span class="tt-status-dot disconnected"></span>'
            '<span class="tt-status-label disconnected">● Disconnected</span>'
            "</div>",
            unsafe_allow_html=True,
        )
    st.divider()

    st.markdown(
        '<div class="tt-sidebar-section">🕐 Recent Searches</div>',
        unsafe_allow_html=True,
    )
    recent = _fetch_recent_searches(st.session_state.session_id)
    if recent:
        for idx, q in enumerate(recent):
            if st.button(q, key=f"recent_{idx}", use_container_width=True):
                _queue_message(q)
                st.rerun()
    else:
        st.markdown(
            '<div class="tt-sidebar-empty">No searches yet.</div>',
            unsafe_allow_html=True,
        )
    st.divider()

    st.markdown(
        '<div class="tt-sidebar-section">💡 Try asking</div>',
        unsafe_allow_html=True,
    )
    for idx, ex in enumerate(EXAMPLE_QUERIES):
        if st.button(ex, key=f"ex_{idx}", use_container_width=True):
            _queue_message(ex)
            st.rerun()
    st.divider()

    if st.button("🗑️ Clear Chat", key="clear_chat", use_container_width=True):
        _clear_session(st.session_state.session_id)
        st.session_state.chat_history = []
        st.session_state.pending_message = None
        st.session_state.error_banner = None
        _fetch_health.clear()
        st.rerun()


# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------
st.markdown(
    '<div class="tt-header">'
    '<h1 class="tt-title">🗂️ TailorTalk Drive Agent</h1>'
    '<div class="tt-subtitle">Your intelligent Google Drive assistant</div>'
    "</div>",
    unsafe_allow_html=True,
)

if st.session_state.error_banner:
    st.markdown(
        f'<div class="tt-error-banner">⚠️ {_esc(st.session_state.error_banner)}</div>',
        unsafe_allow_html=True,
    )
    st.session_state.error_banner = None

# Render existing chat history
for idx, msg in enumerate(st.session_state.chat_history):
    if msg["role"] == "user":
        _render_user_bubble(msg["content"])
    else:
        _render_assistant_bubble(msg["content"])
        _render_assistant_extras(
            msg.get("meta") or {}, key_prefix=f"hist_{idx}"
        )

# Resolve the next prompt: live chat_input OR a queued message
queued = st.session_state.pending_message
st.session_state.pending_message = None
user_input = st.chat_input("Ask me to find any file in your Drive...")
prompt = user_input or queued

if prompt:
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    _render_user_bubble(prompt)

    with st.spinner(_loading_message(prompt)):
        try:
            result = _send_chat(prompt)
        except requests.exceptions.RequestException as e:
            st.session_state.error_banner = (
                "Couldn't reach the search service. Please try again in a moment."
            )
            result = None
        except Exception:
            st.session_state.error_banner = (
                "Something went wrong on our end. Please try again."
            )
            result = None

    if result is None:
        apology = (
            "Sorry — I couldn't reach the search service. "
            "Please try again in a moment."
        )
        _render_assistant_bubble(apology)
        st.session_state.chat_history.append(
            {"role": "assistant", "content": apology, "meta": {}}
        )
    else:
        response_text = result.get("response") or ""
        meta = {
            "query_used": result.get("query_used") or "",
            "reasoning": result.get("reasoning") or "",
            "files": result.get("files") or [],
            "suggestions": result.get("suggestions") or [],
            "search_performed": bool(result.get("search_performed")),
        }
        _render_assistant_bubble(response_text)
        _render_assistant_extras(meta, key_prefix="new")
        st.session_state.chat_history.append(
            {"role": "assistant", "content": response_text, "meta": meta}
        )
        # Rerun so the sidebar's recent-searches reflects this turn
        st.rerun()
