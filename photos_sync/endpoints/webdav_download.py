"""Concurrent WebDAV ingestion endpoint."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from .. import repository as repo
from .. import web_server as _shared
from ..auth import require_admin
from ..observability import (
    WEBDAV_ACTIVE_TRANSFERS,
    WEBDAV_BYTES_RECEIVED,
    WEBDAV_FILES_COMPLETED,
    WEBDAV_FILES_FAILED,
    WEBDAV_FILES_QUEUED,
    WEBDAV_FILES_TOTAL,
    WEBDAV_JOB_DURATION,
    WEBDAV_JOBS,
    WEBDAV_JOBS_RUNNING,
    WEBDAV_LAST_JOB_SUCCESS,
    WEBDAV_LAST_JOB_TIMESTAMP,
    WEBDAV_PHOTOS,
    WEBDAV_RESUMED_TRANSFERS,
    WEBDAV_WORKERS_CONFIGURED,
    log_event,
)

WebDAVScanIn = _shared.WebDAVScanIn
broadcaster = _shared.broadcaster
_webdav_job = _shared._webdav_job
_webdav_job_lock = _shared._webdav_job_lock

router = APIRouter()


@router.post("/api/webdav/download")
def webdav_download(req: WebDAVScanIn, _auth: dict = Depends(require_admin)):
    return _start_webdav_download(req)


@router.post("/api/webdav/download/retry-failed")
def webdav_retry_failed(_auth: dict = Depends(require_admin)):
    """Retry only files that failed in the latest WebDAV job."""
    with _webdav_job_lock:
        if _webdav_job.get("running"):
            raise HTTPException(409, "A WebDAV download is already in progress")
        failed_files = deepcopy(_webdav_job.get("failed_files", []))
        source = dict(_webdav_job.get("source", {}))

    if not failed_files or not source:
        raise HTTPException(409, "There are no failed WebDAV photos to retry")

    req = WebDAVScanIn(
        ip=source["ip"],
        port=str(source["port"]),
        dest_folder=source.get("dest_folder", ""),
        include_videos=bool(source.get("include_videos", True)),
    )
    return _start_webdav_download(req, retry_files=failed_files)


def _start_webdav_download(req: WebDAVScanIn, retry_files: list[dict] | None = None):
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
    from ..storage.webdav_downloader import (
        DEFAULT_REMOTE_PATHS,
        RemoteFile,
        list_remote_files,
        non_overlapping_remote_paths,
    )

    dest = Path(req.dest_folder) if req.dest_folder else ORGANIZED_DIR / "incoming"
    if not _shared._is_allowed(dest):
        raise HTTPException(403, "Destination must be inside a configured photo library")
    dest.mkdir(parents=True, exist_ok=True)
    workers = max(1, min(int(os.getenv("WEBDAV_DOWNLOAD_WORKERS", "32")), 32))
    batch_size = max(1, min(int(os.getenv("WEBDAV_DB_BATCH_SIZE", "250")), 1000))
    chunk_size = max(
        64 * 1024,
        min(int(os.getenv("WEBDAV_CHUNK_SIZE_KB", "2048")) * 1024, 8 * 1024 * 1024),
    )

    is_retry = retry_files is not None
    global _webdav_job
    with _webdav_job_lock:
        if _webdav_job.get("running"):
            raise HTTPException(409, "A WebDAV download is already in progress")
        attempt = int(_webdav_job.get("attempt", 0)) + 1
        _webdav_job.update({
            "running": True, "done": False, "error": None,
            "total": 0, "downloaded": 0, "registered": 0,
            "skipped": 0, "failed": 0, "completed": 0,
            "queued": 0, "resumed": 0,
            "workers": workers, "batch_size": batch_size, "chunk_size": chunk_size,
            "started_at": _t.time(), "finished_at": None,
            "dest": str(dest), "current_file": "",
            "source": {
                "ip": req.ip,
                "port": str(req.port),
                "dest_folder": str(dest),
                "include_videos": req.include_videos,
            },
            "excluded_videos": 0,
            "active_files": {}, "recent_files": [], "failed_files": [],
            "retry_available": False, "retrying": is_retry, "attempt": attempt,
        })

    broadcaster.emit(
        (f"Retrying {len(retry_files or [])} failed WebDAV photos " if is_retry else
         f"Scanning {req.ip}:{req.port} for photos ")
        + f"({workers} download workers)...\n"
    )

    def _worker():
        job_status = "success"
        job_started = _t.perf_counter()
        thread_state = threading.local()
        pending_records: list[dict] = []
        WEBDAV_JOBS_RUNNING.inc()
        WEBDAV_WORKERS_CONFIGURED.set(workers)
        WEBDAV_FILES_TOTAL.set(0)
        WEBDAV_FILES_QUEUED.set(0)
        WEBDAV_ACTIVE_TRANSFERS.set(0)
        WEBDAV_FILES_COMPLETED.set(0)
        WEBDAV_FILES_FAILED.set(0)
        log_event(
            "webdav_job_started",
            destination=str(dest),
            workers=workers,
            db_batch_size=batch_size,
            chunk_size_bytes=chunk_size,
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
            with _webdav_job_lock:
                _webdav_job["registered"] += len(pending_records)
            pending_records.clear()

        try:
            if retry_files is None:
                # Independent roots are scanned concurrently. Results are sorted
                # before naming so duplicate-name handling stays deterministic.
                scan_roots = non_overlapping_remote_paths(DEFAULT_REMOTE_PATHS)
                scan_workers = min(4, len(scan_roots))
                scan_results = []
                with ThreadPoolExecutor(
                    max_workers=scan_workers,
                    thread_name_prefix="webdav-scan",
                ) as scan_pool:
                    future_to_path = {
                        scan_pool.submit(list_remote_files, req.ip, req.port, path): path
                        for path in scan_roots
                    }
                    for future in as_completed(future_to_path):
                        remote_path = future_to_path[future]
                        found = future.result()
                        scan_results.extend(found)
                        if found:
                            broadcaster.emit(f"   {remote_path}: {len(found)} photos\n")

                by_href = {remote.href: remote for remote in scan_results if remote.href}
                all_files = sorted(by_href.values(), key=lambda remote: remote.href.casefold())
            else:
                all_files = [
                    RemoteFile(
                        href=item["href"],
                        name=item["name"],
                        size=int(item.get("size", 0)),
                        modified=item.get("modified", ""),
                    )
                    for item in retry_files
                ]
            if not req.include_videos:
                videos = [remote for remote in all_files if remote.name.lower().endswith(".mp4")]
                all_files = [
                    remote for remote in all_files if not remote.name.lower().endswith(".mp4")
                ]
                with _webdav_job_lock:
                    _webdav_job["excluded_videos"] = len(videos)
                if videos:
                    broadcaster.emit(f"Skipping {len(videos)} MP4 videos by request.\n")
            with _webdav_job_lock:
                _webdav_job["total"] = len(all_files)
                _webdav_job["queued"] = len(all_files)
            WEBDAV_FILES_TOTAL.set(len(all_files))
            WEBDAV_FILES_QUEUED.set(len(all_files))
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

            def register_local(local: Path) -> None:
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

            # Do not spend HTTP worker slots on files already complete on disk.
            # This makes repeated/incremental synchronization proportional to
            # new files rather than the complete phone library size.
            download_candidates: list[RemoteFile] = []
            prechecked: list[tuple[RemoteFile, Path]] = []
            for remote in all_files:
                local = local_by_href[remote.href]
                try:
                    complete = (
                        remote.size > 0
                        and local.is_file()
                        and local.stat().st_size == remote.size
                    )
                except OSError:
                    complete = False
                if complete:
                    prechecked.append((remote, local))
                else:
                    download_candidates.append(remote)

            if prechecked:
                recent = [
                    {
                        "href": remote.href,
                        "name": remote.name,
                        "size": remote.size,
                        "modified": remote.modified,
                        "transferred": 0,
                        "resumed_from": 0,
                        "status": "skipped",
                        "error": None,
                    }
                    for remote, _local in prechecked[-20:]
                ]
                with _webdav_job_lock:
                    _webdav_job["skipped"] = len(prechecked)
                    _webdav_job["completed"] = len(prechecked)
                    _webdav_job["queued"] = len(download_candidates)
                    _webdav_job["recent_files"] = list(reversed(recent))
                for _remote, local in prechecked:
                    if str(local) not in existing:
                        register_local(local)
                flush_records()
                broadcaster.emit(
                    f"Prechecked {len(prechecked)} existing files; "
                    f"{len(download_candidates)} require transfer.\n"
                )

            WEBDAV_FILES_QUEUED.set(len(download_candidates))
            WEBDAV_FILES_COMPLETED.set(len(prechecked))
            broadcaster.emit(
                f"Downloading {len(download_candidates)} pending files to {dest} "
                f"with {workers} workers...\n"
            )

            base_url = f"http://{req.ip}:{req.port}"

            def transfer(remote):
                local = local_by_href[remote.href]
                item = {
                    "href": remote.href,
                    "name": remote.name,
                    "size": remote.size,
                    "modified": remote.modified,
                    "transferred": 0,
                    "resumed_from": 0,
                    "status": "downloading",
                    "error": None,
                }
                with _webdav_job_lock:
                    _webdav_job["active_files"][remote.href] = item
                    _webdav_job["queued"] = max(0, _webdav_job["queued"] - 1)
                WEBDAV_ACTIVE_TRANSFERS.inc()
                WEBDAV_FILES_QUEUED.dec()
                try:
                    if local.exists() and remote.size > 0 and local.stat().st_size == remote.size:
                        return remote, local, "skipped", None
                    url = base_url.rstrip("/") + "/" + remote.href.lstrip("/")
                    temporary = local.with_name(f"{local.name}.webdav.part")
                    resume_from = temporary.stat().st_size if temporary.exists() else 0
                    if remote.size > 0 and resume_from > remote.size:
                        temporary.unlink()
                        resume_from = 0
                    with _webdav_job_lock:
                        item["transferred"] = resume_from
                        item["resumed_from"] = resume_from

                    headers = {}
                    if resume_from:
                        headers = {
                            "Range": f"bytes={resume_from}-",
                            "Accept-Encoding": "identity",
                        }
                    with session_for_thread().get(
                        url,
                        headers=headers,
                        stream=True,
                        timeout=(10, 120),
                    ) as response:
                        if response.status_code == 416 and remote.size == resume_from:
                            temporary.replace(local)
                            return remote, local, "downloaded", None
                        response.raise_for_status()
                        append = bool(resume_from and response.status_code == 206)
                        if append:
                            with _webdav_job_lock:
                                _webdav_job["resumed"] += 1
                            WEBDAV_RESUMED_TRANSFERS.inc()
                        elif resume_from:
                            resume_from = 0
                            with _webdav_job_lock:
                                item["transferred"] = 0
                                item["resumed_from"] = 0
                        with open(temporary, "ab" if append else "wb") as file_handle:
                            for chunk in response.iter_content(chunk_size=chunk_size):
                                if chunk:
                                    file_handle.write(chunk)
                                    WEBDAV_BYTES_RECEIVED.inc(len(chunk))
                                    with _webdav_job_lock:
                                        active = _webdav_job["active_files"].get(remote.href)
                                        if active is not None:
                                            active["transferred"] += len(chunk)
                    if remote.size > 0 and temporary.stat().st_size != remote.size:
                        raise OSError(
                            f"Incomplete WebDAV response for {remote.name}: "
                            f"expected {remote.size} bytes, got {temporary.stat().st_size}"
                        )
                    temporary.replace(local)
                    return remote, local, "downloaded", None
                except Exception as exc:
                    return remote, local, "failed", str(exc)

            with ThreadPoolExecutor(
                max_workers=workers,
                thread_name_prefix="webdav-download",
            ) as download_pool:
                futures = [
                    download_pool.submit(transfer, remote)
                    for remote in download_candidates
                ]
                for future in as_completed(futures):
                    remote, local, outcome, error = future.result()
                    WEBDAV_ACTIVE_TRANSFERS.dec()
                    WEBDAV_FILES_COMPLETED.inc()
                    if error:
                        WEBDAV_FILES_FAILED.inc()
                    with _webdav_job_lock:
                        active = _webdav_job["active_files"].pop(remote.href, {})
                        item = {
                            "href": remote.href,
                            "name": remote.name,
                            "size": remote.size,
                            "modified": remote.modified,
                            "transferred": active.get("transferred", 0),
                            "resumed_from": active.get("resumed_from", 0),
                            "status": outcome,
                            "error": error,
                        }
                        _webdav_job["current_file"] = remote.name
                        _webdav_job["completed"] += 1
                        _webdav_job[outcome] += 1
                        if error:
                            _webdav_job["failed_files"].append(item)
                        else:
                            _webdav_job["recent_files"].insert(0, item)
                            del _webdav_job["recent_files"][20:]

                    if error:
                        broadcaster.emit(f"   Skip {remote.name}: {error}\n")
                    elif str(local) not in existing:
                        register_local(local)

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
            with _webdav_job_lock:
                failed_count = _webdav_job["failed"]
            if failed_count:
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
            with _webdav_job_lock:
                final_state = deepcopy(_webdav_job)
            for outcome in ("downloaded", "registered", "skipped", "failed"):
                WEBDAV_PHOTOS.labels(outcome=outcome).inc(final_state[outcome])
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
                _webdav_job["active_files"] = {}
                _webdav_job["queued"] = 0
                _webdav_job["retry_available"] = bool(_webdav_job["failed_files"])
            WEBDAV_ACTIVE_TRANSFERS.set(0)
            WEBDAV_FILES_QUEUED.set(0)

    threading.Thread(target=_worker, daemon=True, name="webdav-job").start()
    return {
        "ok": True,
        "started": True,
        "message": (
            "Retry of failed WebDAV photos started."
            if is_retry else "Concurrent WebDAV download started."
        ),
        "retrying": is_retry,
        "dest_folder": str(dest),
        "workers": workers,
        "db_batch_size": batch_size,
        "chunk_size_bytes": chunk_size,
    }
