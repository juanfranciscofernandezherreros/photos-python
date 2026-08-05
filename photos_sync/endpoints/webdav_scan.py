"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from ..web_server import (
    Depends,
    WebDAVScanIn,
    require_admin,
)

router = APIRouter()

@router.post("/api/webdav/scan")
def webdav_scan(req: WebDAVScanIn, _auth: dict = Depends(require_admin)):
    """List all photos available on a phone WebDAV server (no download yet).
    Works on any OS — uses direct HTTP, no 'net use' needed."""
    from ..storage.webdav_downloader import DEFAULT_REMOTE_PATHS, list_remote_files
    all_files = []
    seen: set[str] = set()
    for rpath in DEFAULT_REMOTE_PATHS:
        found = list_remote_files(req.ip, req.port, rpath)
        for f in found:
            if f.name not in seen:
                all_files.append({"name": f.name, "size": f.size, "path": f.href})
                seen.add(f.name)
    return {"ok": True, "count": len(all_files), "files": all_files}
