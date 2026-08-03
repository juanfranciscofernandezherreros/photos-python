"""
web_server.py — Local web interface for Photos Sync.

The JS UI is pure presentation: it collects form fields, calls a Python
endpoint, and renders the response. All business logic (validations,
persistence, pipeline state, SSH roles, etc.) lives in Python.

Run headless:
    python -m photos_sync.web_server   →   http://localhost:8765
"""
from __future__ import annotations

import asyncio
import io
import sys
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends, Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from . import repository as repo
from . import auth
from .auth import require_login, require_admin
from .db import init_db
from fastapi.responses import HTMLResponse
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel

# Added imports for fixes
import logging
import os
import secrets
import tempfile

logger = logging.getLogger(__name__)

from .storage import connection
from .pipeline import download, organize, classify, compress, summary, upload_ssh
from . import ssh_connection
from .storage.folders import (load_saved_folders, save_folders,
                       load_destination_config, save_destination, save_ssh_destination)
from .keep_awake import prevent_sleep

# ──────────────────────────── Pipeline steps ───────────────────────────────

PASOS: list[tuple[str, Any]] = [
    ("Sync & save captures", download.sync_captures),
    ("Organize by date",    organize.organize_captures_by_date),
    ("Classify photos",     classify.classify_captures),
    ("Compress by day",     compress.compress_folders_by_day),
    ("Generate summary",    summary.generate_daily_summary),
    ("Upload to SSH",       upload_ssh.upload_organized_to_ssh),
]

# ──────────────────────────── LogBroadcaster ───────────────────────────────

class LogBroadcaster:
    """Captures all stdout/stderr writes from pipeline steps and fans them out
    to every active WebSocket subscriber. Also keeps a rolling in-memory
    buffer so late-connecting clients can replay the current session's log.

    Usage:
        broadcaster = LogBroadcaster()
        broadcaster.subscribe(queue)      # called by each WebSocket handler
        broadcaster.unsubscribe(queue)
        broadcaster.emit("some text\n")   # called by _WebIO.write()
        broadcaster.replay(queue)         # sends buffered lines to new client
    """
    MAX_LINES = 2000

    def __init__(self) -> None:
        self._lines: list[str] = []
        self._listeners: set[asyncio.Queue] = set()
        self._lock = threading.Lock()

    def emit(self, text: str) -> None:
        """Append text to the buffer and push to all current subscribers."""
        with self._lock:
            self._lines.append(text)
            if len(self._lines) > self.MAX_LINES:
                del self._lines[:-self.MAX_LINES]
        for q in list(self._listeners):
            try:
                q.put_nowait(text)
            except Exception:
                pass

    def subscribe(self, q: asyncio.Queue) -> None:
        self._listeners.add(q)

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._listeners.discard(q)

    def replay(self, q: asyncio.Queue) -> list[str]:
        """Return a snapshot of buffered lines for replay to a new client."""
        with self._lock:
            return list(self._lines)

    def clear(self) -> None:
        with self._lock:
            self._lines.clear()


# ──────────────────────────── PipelineManager ──────────────────────────────

class PipelineManager:
    """Owns all mutable pipeline state: running flag, step list, executor.

    Responsibilities:
      - Guard against concurrent runs with a threading.Lock
      - Redirect stdout/stderr to the LogBroadcaster for the duration of a run
      - Run steps in a daemon thread; update running flag in the finally block
      - Expose is_running() and run() as the only public API the endpoints need

    Testable in isolation: inject a LogBroadcaster and a custom step list.
    """

    def __init__(
        self,
        broadcaster: LogBroadcaster,
        pasos: list[tuple[str, Any]] | None = None,
    ) -> None:
        self._broadcaster = broadcaster
        self._pasos = pasos if pasos is not None else PASOS
        self._lock = threading.Lock()
        self._running = False

    def is_running(self) -> bool:
        return self._running

    def step_names(self) -> list[str]:
        return [name for name, _ in self._pasos]

    def run(self, indices: list[int] | None = None) -> list[str]:
        """Start the pipeline in a background thread.

        Args:
            indices: step indices to run, or None to run all.

        Returns:
            List of step names that will be executed.

        Raises:
            RuntimeError: if the pipeline is already running.
        """
        with self._lock:
            if self._running:
                raise RuntimeError("Pipeline is already running.")
            self._running = True

        idx_list = indices if indices is not None else list(range(len(self._pasos)))
        selected = [(self._pasos[i][0], self._pasos[i][1])
                    for i in idx_list if 0 <= i < len(self._pasos)]

        def _run_thread() -> None:
            orig_out, orig_err = sys.stdout, sys.stderr
            sys.stdout = sys.stderr = _BroadcastIO(self._broadcaster)
            try:
                with prevent_sleep():
                    for name, fn in selected:
                        self._broadcaster.emit(f"\n{'='*55}\n⏳ STARTING: {name}\n{'='*55}\n")
                        fn()
                self._broadcaster.emit("\n✅ Pipeline finished successfully.\n")
            except Exception:
                self._broadcaster.emit("\n❌ ERROR:\n" + traceback.format_exc())
            finally:
                sys.stdout = orig_out
                sys.stderr = orig_err
                self._running = False

        threading.Thread(target=_run_thread, daemon=True, name="pipeline").start()
        return [name for name, _ in selected]


# ──────────────────────────── I/O redirect ───────────────────────────────

class _BroadcastIO(io.TextIOBase):
    """Thin TextIO shim that forwards all writes to a LogBroadcaster."""
    def __init__(self, broadcaster: LogBroadcaster) -> None:
        self._broadcaster = broadcaster

    def write(self, s: str) -> int:
        if s:
            self._broadcaster.emit(s)
        return len(s)

    def flush(self) -> None:
        pass


# ──────────────────────────── Singletons ────────────────────────────────

broadcaster = LogBroadcaster()
pipeline    = PipelineManager(broadcaster)
_net_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="net-use")

# ──────────────────────────── FastAPI app ────────────────────────────────

@asynccontextmanager
async def _lifespan(app: FastAPI):
    init_db()  # create tables if they don't exist
    yield

app = FastAPI(title="Photos Sync Web", lifespan=_lifespan)

# ── Rate limiter ─────────────────────────────────────────────────────────
# Uses in-memory storage by default (resets on restart, good enough for a
# single-instance deployment). Key function: client IP address.
# Disabled automatically during testing (TESTING env var = "1").
import os as _os_rl
_TESTING = _os_rl.environ.get("TESTING", "0") == "1"

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    enabled=not _TESTING,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Session cookie for authentication. SECRET_KEY must be stable across
# restarts in production (set it in .env); otherwise sessions are dropped
# on every restart.
import os as _os
_SECRET = _os.environ.get("SECRET_KEY")
if not _SECRET:
    import secrets as _secrets
    _SECRET = _secrets.token_hex(32)
    print("⚠️  SECRET_KEY not set — generated a random one. "
          "Sessions will reset on restart. Set SECRET_KEY in .env for production.")
app.add_middleware(
    SessionMiddleware,
    secret_key=_SECRET,
    session_cookie="photos_session",
    max_age=60 * 60 * 24 * 14,   # 14 days
    same_site="lax",
)


# ═══════════════════════════════════════════ Authentication ════════════════

# ── Username-based lockout (in-memory) ───────────────────────────────────────
# Tracks consecutive login failures per username. After MAX_FAILURES
# consecutive wrong attempts the account is locked for LOCKOUT_SECONDS.
# Resets on server restart — intentional for a single-instance app.
import time as _time
from collections import defaultdict as _defaultdict

_MAX_FAILURES    = 10
_LOCKOUT_SECONDS = 15 * 60   # 15 minutes

# username → {"failures": int, "locked_until": float}
_login_failures: dict = _defaultdict(lambda: {"failures": 0, "locked_until": 0.0})


def _check_lockout(username: str) -> None:
    state = _login_failures[username.lower()]
    if state["locked_until"] > _time.time():
        remaining = int(state["locked_until"] - _time.time())
        raise HTTPException(
            429,
            f"Account temporarily locked due to too many failed attempts. "
            f"Try again in {remaining} seconds."
        )


def _record_failure(username: str) -> None:
    state = _login_failures[username.lower()]
    state["failures"] += 1
    if state["failures"] >= _MAX_FAILURES:
        state["locked_until"] = _time.time() + _LOCKOUT_SECONDS


def _clear_failures(username: str) -> None:
    _login_failures[username.lower()] = {"failures": 0, "locked_until": 0.0}


# ── Lockout status endpoint (admin only) ─────────────────────────────────────

@app.get("/api/auth/lockouts")
def get_lockouts(_admin: dict = Depends(require_admin)):
    """Return all currently locked-out usernames and their unlock time."""
    now = _time.time()
    return {
        "lockouts": [
            {
                "username":       u,
                "failures":       s["failures"],
                "locked_until":   int(s["locked_until"]),
                "remaining_secs": max(0, int(s["locked_until"] - now)),
            }
            for u, s in _login_failures.items()
            if s["locked_until"] > now
        ]
    }


@app.delete("/api/auth/lockouts/{username}")
def unlock_user(username: str, _admin: dict = Depends(require_admin)):
    """Admin can manually unlock a locked-out account."""
    _clear_failures(username)
    return {"ok": True}

# (rest of file unchanged until replacements)

# Replacements: robust _allowed_bases, _is_allowed, and improved serve_photo & serve_thumbnail

def _allowed_bases() -> list[Path]:
    """All directories from which photos may be served.

    Builds a list of resolved base paths including ORGANIZED_DIR, any
    configured destination, saved destination and the THUMBS_DIR so that
    thumbnails are served only from allowed locations.
    """
    from .config import THUMBS_DIR, ORGANIZED_DIR
    from .storage.folders import load_saved_destination, load_destination_config

    bases: list[Path] = []
    try:
        bases.append(Path(ORGANIZED_DIR).resolve())
    except Exception:
        bases.append(Path(ORGANIZED_DIR))

    dc = load_destination_config()
    if dc.get("tipo") == "local" and dc.get("ruta"):
        try:
            bases.append(Path(dc["ruta"]).resolve())
        except Exception:
            bases.append(Path(dc["ruta"]))

    ds = load_saved_destination()
    if ds:
        try:
            bases.append(Path(ds).resolve())
        except Exception:
            bases.append(Path(ds))

    # Ensure THUMBS_DIR is included
    try:
        tb = Path(THUMBS_DIR).resolve()
        if tb not in bases:
            bases.append(tb)
    except Exception:
        pass

    # Deduplicate while preserving order
    unique = []
    seen = set()
    for b in bases:
        s = str(b)
        if s not in seen:
            seen.add(s)
            unique.append(b)
    return unique


def _is_allowed(p: Path) -> bool:
    """Return True if path `p` is inside one of the allowed base paths.

    Uses Path.resolve() + is_relative_to when available. Falls back to string
    prefix comparison guarded by path separator to avoid partial matches.
    """
    try:
        p_res = p.resolve()
    except Exception:
        try:
            p_res = Path(str(p)).resolve()
        except Exception:
            return False

    for base in _allowed_bases():
        try:
            base_res = base.resolve()
        except Exception:
            base_res = base
        try:
            # Python 3.9+: Path.is_relative_to
            if p_res == base_res or p_res.is_relative_to(base_res):
                return True
        except AttributeError:
            base_str = str(base_res)
            p_str = str(p_res)
            # Ensure we match whole path segments: base + os.sep or exact equality
            if p_str == base_str or p_str.startswith(base_str + os.sep):
                return True
    return False


@app.get("/api/photo")
def serve_photo(path: str, _auth: dict = Depends(require_login)):
    """Serve a full-resolution photo file by its absolute path.
    Allows files inside ORGANIZED_DIR or the user-configured destination.
    Adds Cache-Control and an ETag computed from path + mtime.
    """
    from fastapi.responses import FileResponse
    import mimetypes
    import hashlib
    from datetime import datetime

    p = Path(path)
    if not _is_allowed(p):
        logger.warning("Denied access to path outside allowed bases: %s", path)
        raise HTTPException(403, "Access denied — path not inside any configured destination")
    if not p.is_file():
        raise HTTPException(404, "File not found")
    mime = mimetypes.guess_type(p.name)[0] or "image/jpeg"

    try:
        mtime = int(p.stat().st_mtime)
    except OSError:
        mtime = 0
    etag = hashlib.sha1(f"{p.resolve()}|{mtime}".encode("utf-8")).hexdigest()
    headers = {
        "Cache-Control": "public, max-age=86400",
        "ETag": etag,
        "Last-Modified": datetime.utcfromtimestamp(mtime).strftime("%a, %d %b %Y %H:%M:%S GMT"),
    }
    logger.debug("Serving photo %s (ETag=%s)", p, etag)
    return FileResponse(p, media_type=mime, headers=headers)


@app.get("/api/thumb")
def serve_thumbnail(path: str, size: int = 300, _auth: dict = Depends(require_login)):
    """Serve a cached JPEG thumbnail of a photo. Generates and caches it
    on first request under THUMBS_DIR/<hash>.jpg using an atomic write
    (write to temp file then os.replace). Adds Cache-Control + ETag.
    Falls back to the original if Pillow is unavailable or generation fails.
    """
    from .config import THUMBS_DIR
    from fastapi.responses import FileResponse
    import hashlib
    import mimetypes
    try:
        from PIL import Image, UnidentifiedImageError
    except Exception:
        Image = None
        UnidentifiedImageError = Exception

    p = Path(path)
    if not _is_allowed(p):
        logger.warning("Denied thumbnail access to path outside allowed bases: %s", path)
        raise HTTPException(403, "Access denied")
    if not p.is_file():
        raise HTTPException(404, "File not found")

    size = max(64, min(size, 1024))  # clamp

    try:
        mtime = int(p.stat().st_mtime)
    except OSError:
        mtime = 0
    key = f"{p.resolve()}|{size}|{mtime}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()

    THUMBS_DIR.mkdir(parents=True, exist_ok=True)
    thumb_path = THUMBS_DIR / f"{digest}.jpg"

    if thumb_path.exists():
        headers = {"Cache-Control": "public, max-age=86400", "ETag": digest}
        logger.debug("Thumbnail cache hit for %s", thumb_path)
        return FileResponse(thumb_path, media_type="image/jpeg", headers=headers)

    if Image is None:
        logger.warning("Pillow not available, serving original for %s", p)
        mime = mimetypes.guess_type(p.name)[0] or "image/jpeg"
        return FileResponse(p, media_type=mime)

    tmp_suffix = f".tmp-{secrets.token_hex(6)}"
    tmp_path = thumb_path.with_suffix(thumb_path.suffix + tmp_suffix)
    try:
        with Image.open(p) as img:
            img = img.convert("RGB")
            img.thumbnail((size, size), Image.LANCZOS)
            img.save(tmp_path, "JPEG", quality=82, optimize=True)
        # Atomic replace
        os.replace(tmp_path, thumb_path)
        headers = {"Cache-Control": "public, max-age=86400", "ETag": digest}
        logger.info("Generated thumbnail %s from %s", thumb_path, p)
        return FileResponse(thumb_path, media_type="image/jpeg", headers=headers)
    except UnidentifiedImageError:
        logger.exception("Pillow cannot identify image, serving original: %s", p)
    except Exception:
        logger.exception("Error generating thumbnail for %s", p)
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass

    mime = mimetypes.guess_type(p.name)[0] or "image/jpeg"
    logger.debug("Serving original image as fallback for %s", p)
    return FileResponse(p, media_type=mime)


# ──────────────────────────── HTML inline ───────────────────────────────
# El JS solo hace tres cosas:
#   1. Llamar a un endpoint Python al interactuar el usuario.
#   2. Renderizar la respuesta que devuelve Python.
#   3. Gestionar el estado visual mínimo (spinner, habilitar/deshabilitar botones).
# Toda la lógica de negocio, validaciones y estado vive en Python.

_HTML_PATH = Path(__file__).parent / "web" / "static" / "index.html"
_HTML = _HTML_PATH.read_text(encoding="utf-8") if _HTML_PATH.exists() else "<h1>Missing index.html</h1>"




if __name__ == "__main__":
    import uvicorn as _uv
    _uv.run(app, host="127.0.0.1", port=WEB_PORT)
