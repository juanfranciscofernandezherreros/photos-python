"""Concurrent WebDAV ingestion endpoint."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from .. import repository as repo
from .. import web_server as _shared
from ..auth import require_admin
from ..observability import (
    WEBDAV_JOB_DURATION,
    WEBDAV_JOBS,
    WEBDAV_JOBS_RUNNING,
    WEBDAV_LAST_JOB_SUCCESS,
    WEBDAV_LAST_JOB_TIMESTAMP,
    WEBDAV_PHOTOS,
    log_event,
)

WebDAVScanIn = _shared.WebDAVScanIn
broadcaster = _shared.broadcaster
_webdav_job = _shared._webdav_job
_webdav_job_lock = _shared._webdav_job_lock

router = APIRouter()


@router.post("/api/webdav/download")
def webdav_download(req: WebDAVScanIn, _auth: dict = Depends(require_admin)):
    """Scan and download WebDAV photos with bounded parallelism.

    Network transfers run concurrently while all job-state and database writes
    remain serialized in the coordinator thread. Captures are persisted in
    batches, preserving partial progress without one transaction per photo.
    """
    import hashlib
    import os
    import threading
    import time as _t
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from requests import Session
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    from ..config import ORGANIZED_DIR
    from ..storage.webdav_downloader import DEFAULT_REMOTE_PATHS, list_remote_files

    dest = Path(req.dest_folder) if req.dest_folder else ORGANIZED_DIR / "incoming"
    dest.mkdir(parents=True, exist_ok=True)
    workers = max(1, min(int(os.getenv("WEBDAV_DOWNLOAD_WORKERS", "6")), 16))
    batch_size = max(1, min(int(os.getenv("WEBDAV_DB_BATCH_SIZE", "100")), 1000))

    global _webdav_job
    with _webdav_job_lock:
        if _webdav_job.get("running"):
            raise HTTPException(409, "A WebDAV download is already in progress")
        _webdav_job.update({
            "running": True, "done": False, "error": None,
            "total": 0, "downloaded": 0, "registered": 0,
            "skipped": 0, "failed": 0, "completed": 0,
            "workers": workers, "batch_size": batch_size,
            "started_at": _t.time(), "finished_at": None,
            "dest": str(dest), "current_file": "",
        })

    broadcaster.emit(
        f"Scanning {req.ip}:{req.port} for photos "
        f"({workers} download workers)...\n"
    )

    def _worker():
        job_status = "success"
        job_started = _t.perf_counter()
        thread_state = threading.local()
        pending_records: list[dict] = []
        WEBDAV_JOBS_RUNNING.inc()
        log_event(
            "webdav_job_started",
            destination=str(dest),
            workers=workers,
            db_batch_size=batch_size,
        )

        def session_for_thread() -> Session:
            session = getattr(thread_state, "session", None)
            if session is None:
                retry = Retry(
                    total=3,
                    connect=3,
                    read=3,
                    backoff_factor=0.4,
                    status_forcelist=(429, 500, 502, 503, 504),
                    allowed_methods=frozenset({"GET"}),
                )
                session = Session()
                session.mount(
                    "http://",
                    HTTPAdapter(pool_connections=1, pool_maxsize=1, max_retries=retry),
                )
                thread_state.session = session
            return session

        def flush_records() -> None:
            if not pending_records:
                return
            repo.upsert_captures(pending_records)
            _webdav_job["registered"] += len(pending_records)
            pending_records.clear()

        try:
            # Independent roots are scanned concurrently. Results are sorted
            # before naming so duplicate-name handling stays deterministic.
            scan_workers = min(4, len(DEFAULT_REMOTE_PATHS))
            scan_results = []
            with ThreadPoolExecutor(
                max_workers=scan_workers,
                thread_name_prefix="webdav-scan",
            ) as scan_pool:
                future_to_path = {
                    scan_pool.submit(list_remote_files, req.ip, req.port, path): path
                    for path in DEFAULT_REMOTE_PATHS
                }
                for future in as_completed(future_to_path):
                    remote_path = future_to_path[future]
                    found = future.result()
                    scan_results.extend(found)
                    if found:
                        broadcaster.emit(f"   {remote_path}: {len(found)} photos\n")

            by_href = {remote.href: remote for remote in scan_results if remote.href}
            all_files = sorted(by_href.values(), key=lambda remote: remote.href.casefold())
            _webdav_job["total"] = len(all_files)
            if not all_files:
                broadcaster.emit("No photos found on WebDAV server.\n")
                return

            # Flatten into incoming/ while retaining both files when separate
            # remote directories contain the same basename.
            name_totals: dict[str, int] = {}
            for remote in all_files:
                name_totals[remote.name.casefold()] = name_totals.get(remote.name.casefold(), 0) + 1

            local_by_href: dict[str, Path] = {}
            used_names: set[str] = set()
            for remote in all_files:
                local_name = remote.name
                if name_totals[remote.name.casefold()] > 1 or local_name.casefold() in used_names:
                    source_hash = hashlib.sha1(remote.href.encode("utf-8")).hexdigest()[:8]
                    remote_path = Path(remote.name)
                    local_name = f"{remote_path.stem}_{source_hash}{remote_path.suffix}"
                used_names.add(local_name.casefold())
                local_by_href[remote.href] = dest / local_name

            existing = repo.captures_by_destinations([
                str(local_by_href[remote.href]) for remote in all_files
            ])
            broadcaster.emit(
                f"Downloading {len(all_files)} photos to {dest} "
                f"with {workers} workers...\n"
            )

            base_url = f"http://{req.ip}:{req.port}"

            def transfer(remote):
                local = local_by_href[remote.href]
                try:
                    if local.exists() and remote.size > 0 and local.stat().st_size == remote.size:
                        return remote, local, "skipped", None
                    url = base_url.rstrip("/") + "/" + remote.href.lstrip("/")
                    temporary = local.with_name(
                        f"{local.name}.part.{threading.get_ident()}"
                    )
                    try:
                        with session_for_thread().get(url, stream=True, timeout=(10, 120)) as response:
                            response.raise_for_status()
                            with open(temporary, "wb") as file_handle:
                                for chunk in response.iter_content(chunk_size=262_144):
                                    if chunk:
                                        file_handle.write(chunk)
                        temporary.replace(local)
                    except Exception:
                        temporary.unlink(missing_ok=True)
                        raise
                    return remote, local, "downloaded", None
                except Exception as exc:
                    return remote, local, "failed", str(exc)

            with ThreadPoolExecutor(
                max_workers=workers,
                thread_name_prefix="webdav-download",
            ) as download_pool:
                futures = [download_pool.submit(transfer, remote) for remote in all_files]
                for future in as_completed(futures):
                    remote, local, outcome, error = future.result()
                    _webdav_job["current_file"] = remote.name
                    _webdav_job["completed"] += 1
                    _webdav_job[outcome] += 1

                    if error:
                        broadcaster.emit(f"   Skip {remote.name}: {error}\n")
                    elif str(local) not in existing:
                        stat = local.stat()
                        pending_records.append({
                            "id": str(local),
                            "archivo": local.name,
                            "formato": local.suffix.lstrip(".").lower(),
                            "tamano_mb": round(stat.st_size / 1_048_576, 2),
                            "mtime": stat.st_mtime,
                            "fecha_captura": "",
                            "ruta_original": str(local),
                            "ruta_destino": str(local),
                            "tags": [],
                        })
                        existing[str(local)] = pending_records[-1]
                        if len(pending_records) >= batch_size:
                            flush_records()

                    completed = _webdav_job["completed"]
                    if completed % 25 == 0 or completed == len(all_files):
                        flush_records()
                        broadcaster.emit(
                            f"   [{completed}/{len(all_files)}] "
                            f"downloaded={_webdav_job['downloaded']} "
                            f"registered={_webdav_job['registered']} "
                            f"skipped={_webdav_job['skipped']} "
                            f"failed={_webdav_job['failed']}\n"
                        )

            flush_records()
            if _webdav_job["failed"]:
                job_status = "partial"
            broadcaster.emit(
                f"Done. downloaded={_webdav_job['downloaded']} "
                f"registered={_webdav_job['registered']} "
                f"skipped={_webdav_job['skipped']} "
                f"failed={_webdav_job['failed']}\n"
            )
        except Exception as exc:
            job_status = "error"
            import traceback
            traceback.print_exc()
            _webdav_job["error"] = str(exc)
            broadcaster.emit(f"Download failed: {exc}\n")
        finally:
            job_duration = _t.perf_counter() - job_started
            WEBDAV_JOBS_RUNNING.dec()
            WEBDAV_JOBS.labels(status=job_status).inc()
            WEBDAV_JOB_DURATION.labels(status=job_status).observe(job_duration)
            WEBDAV_LAST_JOB_SUCCESS.set(1 if job_status == "success" else 0)
            WEBDAV_LAST_JOB_TIMESTAMP.set(_t.time())
            for outcome in ("downloaded", "registered", "skipped", "failed"):
                WEBDAV_PHOTOS.labels(outcome=outcome).inc(_webdav_job[outcome])
            log_event(
                "webdav_job_finished",
                level="error" if job_status == "error" else "info",
                status=job_status,
                duration_seconds=round(job_duration, 3),
                total=_webdav_job["total"],
                downloaded=_webdav_job["downloaded"],
                registered=_webdav_job["registered"],
                skipped=_webdav_job["skipped"],
                failed=_webdav_job["failed"],
                workers=workers,
            )
            with _webdav_job_lock:
                _webdav_job["running"] = False
                _webdav_job["done"] = True
                _webdav_job["finished_at"] = _t.time()

    threading.Thread(target=_worker, daemon=True, name="webdav-job").start()
    return {
        "ok": True,
        "started": True,
        "message": "Concurrent WebDAV download started.",
        "dest_folder": str(dest),
        "workers": workers,
        "db_batch_size": batch_size,
    }
