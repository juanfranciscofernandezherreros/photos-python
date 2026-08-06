"""Endpoint implemented in its own router module."""
from __future__ import annotations

from copy import deepcopy

from fastapi import APIRouter, Depends

from .. import web_server as _shared
from ..auth import require_admin

# Endpoint implementations retain access to the application's shared services,
# models and state without duplicating business infrastructure.
_webdav_job = _shared._webdav_job
_webdav_job_lock = _shared._webdav_job_lock

router = APIRouter()

_MAX_VISIBLE_FAILURES = 50

@router.get("/api/webdav/download-status")
def webdav_download_status(_auth: dict = Depends(require_admin)):
    """Poll this to know how the background download is going."""
    with _webdav_job_lock:
        status = deepcopy(_webdav_job)

    # Retry uses the complete server-side list directly. Polling clients only
    # need a representative window; returning thousands of failures every
    # second wastes JSON serialization, logging, and browser memory.
    failures = status.get("failed_files", [])
    status["failed_files_total"] = len(failures)
    status["failed_files_truncated"] = len(failures) > _MAX_VISIBLE_FAILURES
    status["failed_files"] = failures[-_MAX_VISIBLE_FAILURES:]
    return status
