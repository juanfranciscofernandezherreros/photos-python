"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from .. import web_server as _shared
from ..auth import require_admin

# Endpoint implementations retain access to the application's shared services,
# models and state without duplicating business infrastructure.
_webdav_job = _shared._webdav_job
_webdav_job_lock = _shared._webdav_job_lock

router = APIRouter()

@router.get("/api/webdav/download-status")
def webdav_download_status(_auth: dict = Depends(require_admin)):
    """Poll this to know how the background download is going."""
    with _webdav_job_lock:
        return dict(_webdav_job)
