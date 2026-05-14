"""Pydantic request/response models for the TailorTalk backend."""

from typing import List

from pydantic import BaseModel, Field


class FileResult(BaseModel):
    """A single file returned by the Drive search tool."""

    id: str = ""
    name: str = ""
    type_label: str = ""
    mime_type: str = ""
    modified_time_formatted: str = ""
    web_view_link: str = ""
    size_formatted: str = ""
    preview_text: str = ""


class ChatRequest(BaseModel):
    """Incoming payload for POST /chat."""

    message: str
    session_id: str
    chat_history: List[dict] = Field(default_factory=list)


class ChatResponse(BaseModel):
    """Response payload for POST /chat."""

    response: str = ""
    files: List[FileResult] = Field(default_factory=list)
    query_used: str = ""
    reasoning: str = ""
    suggestions: List[str] = Field(default_factory=list)
    search_performed: bool = False


class HealthResponse(BaseModel):
    """Response payload for GET /health."""

    status: str = "ok"
    drive_connected: bool = False
    message: str = ""
