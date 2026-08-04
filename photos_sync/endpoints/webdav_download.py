"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from .. import web_server as _shared
from ..observability import (
    WEBDAV_JOB_DURATION,
    WEBDAV_JOBS,
    WEBDAV_JOBS_RUNNING,
    log_event,
)

# Endpoint implementations retain access to the application's shared services,
# models and state without duplicating business infrastructure.
globals().update({
    name: value
    for name, value in vars(_shared).items()
    if not name.startswith("__")
})

router = APIRouter()

@router.post("/api/webdav/download")
def webdav_download(req: WebDAVScanIn, _auth: dict = Depends(require_admin)):
    """Kick off a WebDAV download in a background thread and return immediately.

    Each photo is registered in the `captures` table AS SOON AS it lands on
    disk (not at the end), so the gallery starts filling up right away and
    partial downloads still save what they got.

    Progress is streamed via the WebSocket at /ws/log — the same log the
    Pipeline uses. The response returns immediately with job info so the
    UI can start polling /api/webdav/download-status.
    """
    import threading
    import time as _t

    from ..config import ORGANIZED_DIR
    from ..storage.webdav_downloader import (
        DEFAULT_REMOTE_PATHS,
        list_remote_files,
    )

    dest = Path(req.dest_folder) if req.dest_folder else ORGANIZED_DIR / "incoming"
    dest.mkdir(parents=True, exist_ok=True)

    # Prevent concurrent downloads (simple guard)
    global _webdav_job
    if _webdav_job.get("running"):
        raise HTTPException(409, "A WebDAV download is already in progress")

    # Reset job state
    _webdav_job.update({
        "running": True, "done": False, "error": None,
        "total": 0, "downloaded": 0, "registered": 0, "skipped": 0,
        "started_at": _t.time(), "finished_at": None,
        "dest": str(dest), "current_file": "",
    })
    broadcaster.emit(f"🔍 Scanning {req.ip}:{req.port} for photos…\n")

    def _worker():
        job_status = "success"
        job_started = _t.perf_counter()
        WEBDAV_JOBS_RUNNING.inc()
        log_event("webdav_job_started", destination=str(dest))
        try:
            import requests as _requests
            # 1) List all photos across the default folders
            all_files = []
            seen = set()
            for rpath in DEFAULT_REMOTE_PATHS:
                found = list_remote_files(req.ip, req.port, rpath)
                for f in found:
                    if f.name not in seen:
                        all_files.append(f)
                        seen.add(f.name)
                if found:
                    broadcaster.emit(f"   {rpath}: {len(found)} photos\n")

            _webdav_job["total"] = len(all_files)
            if not all_files:
                broadcaster.emit("⚠️  No photos found on WebDAV server.\n")
                return

            broadcaster.emit(f"📥 Downloading {len(all_files)} photos to {dest}…\n")

            base_url = f"http://{req.ip}:{req.port}"
            for idx, f in enumerate(all_files, 1):
                _webdav_job["current_file"] = f.name
                local = dest / f.name

                # Skip if same-size copy already on disk
                if local.exists() and local.stat().st_size == f.size and f.size > 0:
                    _webdav_job["skipped"] += 1
                else:
                    # Download this one file
                    try:
                        url = base_url.rstrip("/") + "/" + f.href.lstrip("/")
                        r = _requests.get(url, stream=True, timeout=60)
                        r.raise_for_status()
                        tmp = local.with_suffix(local.suffix + ".part")
                        with open(tmp, "wb") as fh:
                            for chunk in r.iter_content(chunk_size=65536):
                                fh.write(chunk)
                        tmp.replace(local)
                        _webdav_job["downloaded"] += 1
                    except Exception as e:
                        broadcaster.emit(f"   ⚠️  Skip {f.name}: {e}\n")
                        continue

                # Register in DB IMMEDIATELY — one row per photo, per iteration.
                # Even if the whole job fails later, what we've got is saved.
                try:
                    path_str = str(local)
                    if not repo.get_capture_by_dest(path_str):
                        stat = local.stat()
                        repo.upsert_captures([{
                            "id":            path_str,
                            "archivo":       f.name,
                            "formato":       Path(f.name).suffix.lstrip(".").lower(),
                            "tamano_mb":     round(stat.st_size / 1048576, 2),
                            "mtime":         stat.st_mtime,
                            "fecha_captura": "",  # upsert_captures derives it from filename
                            "ruta_original": path_str,
                            "ruta_destino":  path_str,
                            "tags":          [],
                        }])
                        _webdav_job["registered"] += 1
                except Exception as e:
                    broadcaster.emit(f"   ⚠️  DB register failed for {f.name}: {e}\n")

                # Progress log every 25 files (not every one — would spam)
                if idx % 25 == 0 or idx == len(all_files):
                    broadcaster.emit(
                        f"   [{idx}/{len(all_files)}] downloaded={_webdav_job['downloaded']} "
                        f"registered={_webdav_job['registered']} skipped={_webdav_job['skipped']}\n"
                    )

            broadcaster.emit(
                f"✅ Done. downloaded={_webdav_job['downloaded']} "
                f"registered={_webdav_job['registered']} skipped={_webdav_job['skipped']}\n"
            )
        except Exception as e:
            job_status = "error"
            import traceback
            traceback.print_exc()
            _webdav_job["error"] = str(e)
            broadcaster.emit(f"❌ Download failed: {e}\n")
        finally:
            job_duration = _t.perf_counter() - job_started
            WEBDAV_JOBS_RUNNING.dec()
            WEBDAV_JOBS.labels(status=job_status).inc()
            WEBDAV_JOB_DURATION.labels(status=job_status).observe(job_duration)
            log_event(
                "webdav_job_finished",
                level="error" if job_status == "error" else "info",
                status=job_status,
                duration_seconds=round(job_duration, 3),
                total=_webdav_job["total"],
                downloaded=_webdav_job["downloaded"],
                registered=_webdav_job["registered"],
                skipped=_webdav_job["skipped"],
            )
            _webdav_job["running"] = False
            _webdav_job["done"] = True
            _webdav_job["finished_at"] = _t.time()

    threading.Thread(target=_worker, daemon=True).start()

    return {
        "ok": True,
        "started": True,
        "message": "Download started in background. Watch progress in the log or poll /api/webdav/download-status.",
        "dest_folder": str(dest),
    }
