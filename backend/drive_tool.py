"""Google Drive integration for TailorTalk.

Handles service-account auth and exposes helpers for searching files inside
a configured Drive folder, fetching short previews, and verifying API
reachability.
"""

import json
import os
import re
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

MIME_TYPE_LABELS = {
    "application/pdf": "PDF",
    "application/vnd.google-apps.document": "Google Doc",
    "application/vnd.google-apps.spreadsheet": "Google Sheet",
    "application/vnd.google-apps.presentation": "Slides",
}

FILE_FIELDS = "id, name, mimeType, modifiedTime, webViewLink, size"
MAX_RESULTS = 10

TYPO_MAP = {
    "spreadshet": "spreadsheet",
    "spreedsheet": "spreadsheet",
    "spredsheet": "spreadsheet",
    "documet": "document",
    "docuemnt": "document",
    "presenation": "presentation",
    "presentaion": "presentation",
    "presetation": "presentation",
    "imge": "image",
    "iamge": "image",
    "pdff": "pdf",
    "pfd": "pdf",
}

_TYPO_PATTERNS = [
    (re.compile(r"\b" + re.escape(typo) + r"\b", re.IGNORECASE), fix)
    for typo, fix in TYPO_MAP.items()
]


def normalize_query_terms(q: str) -> str:
    """Replace common misspellings in a Drive query string.

    Matches are case-insensitive and use word boundaries so we never
    corrupt a substring of a longer token. When at least one correction
    is applied, the change is printed for visibility.
    """
    if not q:
        return q
    corrected = q
    for pattern, fix in _TYPO_PATTERNS:
        corrected = pattern.sub(fix, corrected)
    if corrected != q:
        print(f"Typo corrected: {q} → {corrected}")
    return corrected


def _get_credentials() -> service_account.Credentials:
    """Build service-account credentials from environment.

    Prefers ``GOOGLE_SERVICE_ACCOUNT_JSON`` (raw JSON string — used in
    deployment) and falls back to ``GOOGLE_SERVICE_ACCOUNT_PATH``
    (file path — used locally).
    """
    raw_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if raw_json:
        try:
            info = json.loads(raw_json)
        except json.JSONDecodeError as e:
            raise Exception(f"GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON: {e}")
        return service_account.Credentials.from_service_account_info(
            info, scopes=SCOPES
        )

    path = os.getenv("GOOGLE_SERVICE_ACCOUNT_PATH")
    if not path:
        raise Exception(
            "No service-account credentials found. Set "
            "GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_PATH."
        )
    if not os.path.exists(path):
        raise Exception(f"Service-account file not found at: {path}")
    return service_account.Credentials.from_service_account_file(
        path, scopes=SCOPES
    )


def _get_service():
    """Build and return a Google Drive v3 client."""
    try:
        creds = _get_credentials()
        return build("drive", "v3", credentials=creds, cache_discovery=False)
    except Exception as e:
        raise Exception(f"Failed to initialize Google Drive client: {e}")


def _get_folder_id() -> str:
    """Return the DRIVE_FOLDER_ID env var or raise if missing."""
    folder_id = os.getenv("DRIVE_FOLDER_ID")
    if not folder_id:
        raise Exception("DRIVE_FOLDER_ID is not set in the environment.")
    return folder_id


def _label_for_mime(mime_type: str) -> str:
    """Map a Drive mimeType to a short, human-readable label."""
    if mime_type in MIME_TYPE_LABELS:
        return MIME_TYPE_LABELS[mime_type]
    if mime_type and mime_type.startswith("image/"):
        return "Image"
    return "File"


def _format_modified_time(iso_time: str) -> str:
    """Convert an RFC3339 timestamp to ``May 12, 2025`` form."""
    if not iso_time:
        return ""
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            dt = datetime.strptime(iso_time, fmt)
            return f"{dt.strftime('%b')} {dt.day}, {dt.year}"
        except ValueError:
            continue
    return iso_time


def _format_size(raw_size: Optional[str]) -> str:
    """Convert raw byte count to human-readable KB or MB (e.g. ``1.2 MB``)."""
    if raw_size is None:
        return ""
    try:
        size_bytes = int(raw_size)
    except (TypeError, ValueError):
        return ""
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def search_files(query: str) -> list[dict]:
    """Search the configured Drive folder using a Drive ``q`` expression.

    Args:
        query: A raw Drive ``q`` query (e.g.
            ``"name contains 'budget' and mimeType = 'application/pdf'"``).
            Empty/whitespace yields the folder's most recently modified
            files. The folder-parent and ``trashed = false`` filters are
            always appended automatically.

    Returns:
        Up to 10 file dicts ordered by ``modifiedTime`` desc. Each dict
        contains: ``id``, ``name``, ``mimeType``, ``type``, ``modified``,
        ``size``, ``link``.

    Raises:
        Exception: If credentials are missing, the folder ID is unset,
            or the Drive API call fails.
    """
    folder_id = _get_folder_id()
    service = _get_service()

    query = normalize_query_terms(query or "")
    q_parts = [f"'{folder_id}' in parents", "trashed = false"]
    user_q = query.strip()
    if user_q:
        q_parts.append(f"({user_q})")
    q = " and ".join(q_parts)

    try:
        response = (
            service.files()
            .list(
                q=q,
                fields=f"files({FILE_FIELDS})",
                pageSize=MAX_RESULTS,
                orderBy="modifiedTime desc",
            )
            .execute()
        )
    except HttpError as e:
        raise Exception(f"Google Drive search failed: {e}")
    except Exception as e:
        raise Exception(f"Unexpected error while searching Drive: {e}")

    files = response.get("files", [])
    return [
        {
            "id": f.get("id", ""),
            "name": f.get("name", ""),
            "mimeType": f.get("mimeType", ""),
            "type": _label_for_mime(f.get("mimeType", "")),
            "modified": _format_modified_time(f.get("modifiedTime", "")),
            "size": _format_size(f.get("size")),
            "link": f.get("webViewLink", ""),
        }
        for f in files
    ]


def get_file_preview(file_id: str, mime_type: str) -> str:
    """Return a short text preview of a file.

    Google Docs are exported as ``text/plain`` and truncated to the first
    200 characters. All other mime types return an empty string. Any error
    is swallowed and yields an empty string — this function never raises.

    Args:
        file_id: The Drive file ID.
        mime_type: The file's mimeType.

    Returns:
        A preview string (up to 200 chars) or ``""``.
    """
    if mime_type != "application/vnd.google-apps.document":
        return ""
    try:
        service = _get_service()
        data = (
            service.files()
            .export(fileId=file_id, mimeType="text/plain")
            .execute()
        )
        text = data.decode("utf-8", errors="ignore") if isinstance(data, bytes) else str(data)
        return text[:200]
    except Exception:
        return ""


def check_drive_connection() -> bool:
    """Return ``True`` if the Drive API responds to a lightweight call."""
    try:
        service = _get_service()
        service.files().list(pageSize=1, fields="files(id)").execute()
        return True
    except Exception:
        return False
