"""LangChain agent that drives Google Drive search via Gemini 1.5 Flash.

The agent exposes a single ``DriveSearchTool`` that wraps
``drive_tool.search_files``. ``run_agent`` is the entry point used by the
FastAPI layer — it returns a structured dict containing the user-facing
response together with the underlying Drive query, the files returned,
the agent's reasoning sentence, and two follow-up search suggestions.
"""

import os
import re
from typing import Any, List, Optional, Tuple

from dotenv import load_dotenv
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI

from drive_tool import search_files
from memory import get_memory

load_dotenv()

SYSTEM_PROMPT = """You are TailorTalk Drive Assistant, an intelligent file discovery agent.
Your job is to help users find files in their Google Drive through natural conversation.

QUERY BUILDING RULES:
- Exact name: name = 'filename'
- Partial name: name contains 'keyword'
- PDF: mimeType = 'application/pdf'
- Google Doc: mimeType = 'application/vnd.google-apps.document'
- Google Sheet: mimeType = 'application/vnd.google-apps.spreadsheet'
- Slides: mimeType = 'application/vnd.google-apps.presentation'
- Images: mimeType contains 'image'
- Content search: fullText contains 'keyword'
- Date after: modifiedTime > '2025-01-01T00:00:00'
- Date before: modifiedTime < '2025-01-01T00:00:00'
- Combine with: and, or

BEHAVIOR RULES:
- Always explain in one sentence what you searched for and why
- If results found, summarize what you found before listing files
- If no results found, suggest 2 alternative search approaches the user can try
- If query is ambiguous, ask one clarifying question
- Convert relative dates like "last week", "yesterday", "this month" to actual ISO dates
- Handle typos gracefully — "spreadshet" means spreadsheet
- Never say you cannot do something — always attempt best-effort search
- After every search, suggest 2 follow-up searches the user might find useful
- Keep responses concise and friendly
- Always return your reasoning: one sentence explaining what you searched and why"""

OUTPUT_FORMAT_INSTRUCTIONS = """OUTPUT FORMAT (mandatory):
- Begin your reply with exactly one sentence of reasoning that explains what you searched and why.
- Finish your reply with exactly two follow-up suggestion lines, each on its own line in this form:
  SUGGESTION: <a follow-up search idea>
  SUGGESTION: <a follow-up search idea>
Do not number them. Do not add anything after the last SUGGESTION line."""

FULL_SYSTEM_PROMPT = SYSTEM_PROMPT + "\n\n" + OUTPUT_FORMAT_INSTRUCTIONS

GEMINI_MODEL = "gemini-1.5-flash"

_SUGGESTION_RE = re.compile(r"(?im)^\s*SUGGESTION:\s*(.+?)\s*$")
_GENERIC_SUGGESTIONS = (
    "Try broadening your search with fewer keywords.",
    "Try filtering by file type (e.g. PDF, Google Doc, or Sheet).",
)


@tool
def DriveSearchTool(q: str) -> List[dict]:
    """Search Google Drive within the configured folder.

    Args:
        q: A Drive ``q`` query string built from the QUERY BUILDING RULES
           (e.g. ``"name contains 'budget' and mimeType = 'application/pdf'"``).
           The folder scope and ``trashed = false`` filter are appended
           automatically — do not include them.

    Returns:
        Up to 10 file dicts (``id``, ``name``, ``mimeType``, ``type``,
        ``modified``, ``size``, ``link``) ordered by most recently
        modified.
    """
    return search_files(q)


def _build_llm() -> ChatGoogleGenerativeAI:
    """Construct the Gemini chat model from the GEMINI_API_KEY env var."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise Exception("GEMINI_API_KEY is not set in the environment.")
    return ChatGoogleGenerativeAI(
        model=GEMINI_MODEL,
        google_api_key=api_key,
        temperature=0.2,
    )


def _build_executor(memory) -> AgentExecutor:
    """Wire the prompt, tools, memory, and LLM into an ``AgentExecutor``."""
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", FULL_SYSTEM_PROMPT),
            MessagesPlaceholder("chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ]
    )
    agent = create_tool_calling_agent(_build_llm(), [DriveSearchTool], prompt)
    return AgentExecutor(
        agent=agent,
        tools=[DriveSearchTool],
        memory=memory,
        return_intermediate_steps=True,
        verbose=False,
        handle_parsing_errors=True,
        max_iterations=4,
    )


def _seed_memory(memory, chat_history: Optional[list]) -> None:
    """Populate an empty memory from caller-supplied chat history.

    Expected message shape: ``{"role": "user"|"assistant", "content": "..."}``.
    No-op if memory already has messages or ``chat_history`` is falsy.
    """
    if not chat_history or memory.chat_memory.messages:
        return
    for msg in chat_history:
        if not isinstance(msg, dict):
            continue
        role = (msg.get("role") or "").lower()
        content = msg.get("content", "")
        if not content:
            continue
        if role == "user":
            memory.chat_memory.add_user_message(content)
        elif role in ("assistant", "ai"):
            memory.chat_memory.add_ai_message(content)


def _extract_tool_info(intermediate_steps: list) -> Tuple[str, List[dict]]:
    """Return ``(query_used, files)`` from the most recent DriveSearchTool call."""
    for action, observation in reversed(intermediate_steps or []):
        if getattr(action, "tool", None) != "DriveSearchTool":
            continue
        tool_input: Any = getattr(action, "tool_input", "")
        if isinstance(tool_input, dict):
            query_used = str(tool_input.get("q", "")).strip()
        else:
            query_used = str(tool_input).strip()
        files = observation if isinstance(observation, list) else []
        return query_used, files
    return "", []


def _extract_suggestions_and_clean(text: str) -> Tuple[List[str], str]:
    """Pull ``SUGGESTION:`` lines out of ``text``.

    Returns a tuple of ``(suggestions, cleaned_text)``. Always returns
    exactly two suggestions — falls back to generic ones if the agent
    failed to produce two.
    """
    matches = [m.strip() for m in _SUGGESTION_RE.findall(text) if m.strip()]
    cleaned = _SUGGESTION_RE.sub("", text).strip()
    suggestions = matches[:2]
    while len(suggestions) < 2:
        suggestions.append(_GENERIC_SUGGESTIONS[len(suggestions)])
    return suggestions, cleaned


def _extract_reasoning(text: str) -> str:
    """Return the first sentence (or first line) of the cleaned response."""
    if not text:
        return ""
    first_line = text.strip().splitlines()[0].strip()
    match = re.match(r"^(.+?[.!?])(?:\s|$)", first_line)
    return match.group(1).strip() if match else first_line


def run_agent(
    session_id: str,
    message: str,
    chat_history: Optional[list] = None,
) -> dict:
    """Run the TailorTalk agent for a single user turn.

    Args:
        session_id: Stable per-user session identifier used to look up
            server-side memory.
        message: The user's natural-language message.
        chat_history: Optional caller-supplied prior turns
            (``[{"role": ..., "content": ...}, ...]``) used only to
            seed memory if the server-side session is empty.

    Returns:
        A dict with keys:
        - ``response``: user-facing reply (without the SUGGESTION lines)
        - ``query_used``: the Drive ``q`` string that was sent to the tool
        - ``reasoning``: one-sentence explanation of what was searched
        - ``files``: list of file dicts returned by the tool
        - ``suggestions``: exactly two follow-up search suggestion strings

        On failure, returns a friendly error response with empty files
        and generic fallback suggestions; never raises.
    """
    try:
        memory = get_memory(session_id)
        _seed_memory(memory, chat_history)
        executor = _build_executor(memory)
        result = executor.invoke({"input": message})

        raw_output = result.get("output", "") or ""
        query_used, files = _extract_tool_info(result.get("intermediate_steps", []))
        suggestions, cleaned_output = _extract_suggestions_and_clean(raw_output)
        reasoning = _extract_reasoning(cleaned_output)

        return {
            "response": cleaned_output,
            "query_used": query_used,
            "reasoning": reasoning,
            "files": files,
            "suggestions": suggestions,
        }
    except Exception as e:
        return {
            "response": (
                "Sorry — I ran into a problem reaching the search service. "
                "Please try again in a moment."
            ),
            "query_used": "",
            "reasoning": f"Agent error: {e}",
            "files": [],
            "suggestions": list(_GENERIC_SUGGESTIONS),
        }
