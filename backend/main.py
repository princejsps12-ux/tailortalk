"""FastAPI entry point for the TailorTalk Drive Agent backend."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from agent import run_agent
from drive_tool import check_drive_connection
from memory import (
    add_recent_search,
    cleanup_old_sessions,
    clear_memory,
    get_recent_searches,
)
from models import ChatRequest, ChatResponse, FileResult, HealthResponse

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
logger = logging.getLogger("tailortalk")

CLEANUP_INTERVAL_SECONDS = 30 * 60  # 30 minutes


async def _cleanup_loop() -> None:
    """Periodically expire stale session memory."""
    while True:
        try:
            await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
            removed = cleanup_old_sessions()
            if removed:
                logger.info("cleanup removed %d expired sessions", removed)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("cleanup loop iteration failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run the background cleanup task for the lifetime of the app."""
    task = asyncio.create_task(_cleanup_loop())
    logger.info("started session cleanup task (every %d s)", CLEANUP_INTERVAL_SECONDS)
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


app = FastAPI(title="TailorTalk Drive Agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

limiter = Limiter(key_func=get_remote_address, default_limits=["20/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a clean JSON error for any uncaught exception."""
    logger.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error. Please try again."},
    )


def _to_file_result(item: Dict[str, Any]) -> FileResult:
    """Convert a drive_tool result dict into a ``FileResult`` model."""
    return FileResult(
        id=item.get("id", "") or "",
        name=item.get("name", "") or "",
        type_label=item.get("type", "") or "",
        mime_type=item.get("mimeType", "") or "",
        modified_time_formatted=item.get("modified", "") or "",
        web_view_link=item.get("link", "") or "",
        size_formatted=item.get("size", "") or "",
        preview_text="",
    )


@app.post("/chat", response_model=ChatResponse)
@limiter.limit("20/minute")
async def chat(request: Request, body: ChatRequest) -> ChatResponse:
    """Handle a single chat turn.

    Logs the request, dispatches to the LangChain agent, records the
    Drive query in the session's recent-search list, and returns a
    structured response. Any unexpected error is caught and converted
    into a friendly reply — callers never see a raw traceback.
    """
    logger.info(
        "chat session=%s message=%r",
        body.session_id,
        body.message[:50],
    )

    try:
        result = run_agent(body.session_id, body.message, body.chat_history)
    except Exception:
        logger.exception("run_agent raised unexpectedly")
        return ChatResponse(
            response="Sorry — something went wrong handling that request. Please try again.",
            files=[],
            query_used="",
            reasoning="",
            suggestions=[
                "Try rephrasing your question.",
                "Try a simpler search like a file name.",
            ],
            search_performed=False,
        )

    files = [_to_file_result(f) for f in (result.get("files") or [])]
    query_used = (result.get("query_used") or "").strip()
    if query_used:
        add_recent_search(body.session_id, query_used)

    return ChatResponse(
        response=result.get("response", "") or "",
        files=files,
        query_used=query_used,
        reasoning=result.get("reasoning", "") or "",
        suggestions=list(result.get("suggestions") or []),
        search_performed=bool(query_used) or bool(files),
    )


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Lightweight health check that probes the Drive API."""
    try:
        connected = check_drive_connection()
    except Exception:
        logger.exception("check_drive_connection raised")
        connected = False
    return HealthResponse(
        status="ok" if connected else "degraded",
        drive_connected=connected,
        message=(
            "Drive API reachable."
            if connected
            else "Drive API unreachable — check credentials and folder ID."
        ),
    )


@app.delete("/chat/{session_id}")
async def delete_session(session_id: str) -> Dict[str, str]:
    """Clear conversation memory and recent searches for a session."""
    clear_memory(session_id)
    return {"message": "Session cleared"}


@app.get("/recent-searches/{session_id}")
async def recent_searches(session_id: str) -> Dict[str, List[str]]:
    """Return up to the last 5 unique Drive queries for a session."""
    return {"queries": get_recent_searches(session_id)}
