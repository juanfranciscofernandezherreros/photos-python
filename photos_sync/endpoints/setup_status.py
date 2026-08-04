"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from .. import web_server as _shared

# Endpoint implementations retain access to the application's shared services,
# models and state without duplicating business infrastructure.
globals().update({
    name: value
    for name, value in vars(_shared).items()
    if not name.startswith("__")
})

router = APIRouter()

@router.get("/api/setup-status")
def setup_status():
    """Returns which essential configuration steps are complete.
    Used by the first-run wizard in the frontend."""
    from ..storage import ssh_repo
    from ..storage.connection import load_connections
    from ..storage.folders import load_destination_config

    dest   = load_destination_config()
    webdav = load_connections()
    ssh    = ssh_repo.load_ssh_connections()

    has_dest   = bool(dest.get("tipo"))
    has_source = bool(webdav or ssh)
    is_done    = has_dest and has_source

    return {
        "done":       is_done,
        "has_source": has_source,
        "has_dest":   has_dest,
        "webdav_count": len(webdav),
        "ssh_count":    len(ssh),
        "dest_type":    dest.get("tipo", ""),
        "dest_detail":  dest.get("ruta") or dest.get("alias") or "",
    }
