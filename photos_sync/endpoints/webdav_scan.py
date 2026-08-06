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
    videos = [
        item for item in all_files
        if str(item["name"]).lower().endswith(".mp4")
    ]
    excluded_videos = len(videos)
    if not req.include_videos:
        all_files = [
            item for item in all_files
            if not str(item["name"]).lower().endswith(".mp4")
        ]
    return {
        "ok": True,
        "count": len(all_files),
        "excluded_videos": excluded_videos if not req.include_videos else 0,
        "files": all_files,
    }
