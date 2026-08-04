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
from typing import Any

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.sessions import SessionMiddleware

from . import auth, ssh_connection
from . import repository as repo
from .auth import require_admin, require_login
from .db import init_db
from .keep_awake import prevent_sleep
from .pipeline import classify, compress, download, organize, summary, upload_ssh
from .storage import connection
from .storage.folders import (
    load_destination_config,
    load_saved_folders,
    save_destination,
    save_folders,
    save_ssh_destination,
)

# ──────────────────────────── Pipeline steps ────────────────────────────────

PASOS: list[tuple[str, Any]] = [
    ("Sync & save captures", download.sync_captures),
    ("Organize by date",    organize.organize_captures_by_date),
    ("Classify photos",     classify.classify_captures),
    ("Compress by day",     compress.compress_folders_by_day),
    ("Generate summary",    summary.generate_daily_summary),
    ("Upload to SSH",       upload_ssh.upload_organized_to_ssh),
]

# ──────────────────────────── LogBroadcaster ────────────────────────────────

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


# ──────────────────────────── PipelineManager ───────────────────────────────

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


# ──────────────────────────── I/O redirect ──────────────────────────────────

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


# ──────────────────────────── Singletons ────────────────────────────────────

broadcaster = LogBroadcaster()
pipeline    = PipelineManager(broadcaster)
_net_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="net-use")

# ──────────────────────────── FastAPI app ───────────────────────────────────

@asynccontextmanager
async def _lifespan(app: FastAPI):
    init_db()  # create tables if they don't exist
    yield

app = FastAPI(title="Photos Sync Web", lifespan=_lifespan)

# ── Rate limiter ─────────────────────────────────────────────────────────────
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
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

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


# ═══════════════════════════════════════════ Authentication ═════════════════

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

class AdminSetupIn(BaseModel):
    username: str
    password: str


class LoginIn(BaseModel):
    username: str
    password: str


class CreateUserIn(BaseModel):
    username: str
    password: str
    role: str = "user"


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


@app.get("/api/auth/status")
def auth_status(request: Request):
    """Public. Tells the frontend which screen to show."""
    user = auth.current_user(request)
    return {
        "admin_exists": repo.admin_exists(),
        "authenticated": user is not None,
        "user": {"id": user["id"], "username": user["username"], "role": user["role"]}
                 if user else None,
    }


@app.post("/api/auth/setup-admin")
@limiter.limit("5/minute")
def setup_admin(request: Request, req: AdminSetupIn):
    """Public — but only works once, while no admin exists yet."""
    if repo.admin_exists():
        raise HTTPException(403, "An administrator already exists")
    auth.validate_password_strength(req.password)
    try:
        user = repo.create_user(
            username=req.username,
            password_hash=auth.hash_password(req.password),
            role="admin",
        )
    except repo.AdminExistsError:
        raise HTTPException(403, "An administrator already exists")
    except repo.UsernameTakenError:
        raise HTTPException(400, "Username is already taken")
    except ValueError as e:
        raise HTTPException(400, str(e))
    # Auto-login the new admin
    request.session["user_id"] = user["id"]
    return {"ok": True, "user": user}


@app.post("/api/auth/login")
@limiter.limit("10/minute")
def login(request: Request, req: LoginIn):
    """5 attempts per minute per IP. 10 consecutive failures locks the account
    for 15 minutes (in-memory, resets on server restart)."""
    _check_lockout(req.username)
    user = repo.get_user_by_username((req.username or "").strip())
    if not user or not user.get("active", True) or \
       not auth.verify_password(req.password, user["password_hash"]):
        _record_failure(req.username)
        raise HTTPException(401, "Invalid username or password")
    _clear_failures(req.username)
    request.session["user_id"] = user["id"]
    return {"ok": True, "user": {"id": user["id"], "username": user["username"],
                                  "role": user["role"]}}


@app.post("/api/auth/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@app.get("/api/auth/me")
def auth_me(user: dict = Depends(require_login)):
    return {"user": user}


@app.post("/api/auth/change-password")
def change_password(req: ChangePasswordIn, user: dict = Depends(require_login)):
    full = repo.get_user_by_username(user["username"])
    if not full or not auth.verify_password(req.current_password, full["password_hash"]):
        raise HTTPException(400, "Current password is incorrect")
    auth.validate_password_strength(req.new_password)
    repo.set_user_password(user["id"], auth.hash_password(req.new_password))
    return {"ok": True}


# ── User management (admin only) ─────────────────────────────────────────────

@app.get("/api/users")
def get_users(admin: dict = Depends(require_admin)):
    return {"users": repo.list_users(), "total": repo.user_count()}


@app.post("/api/users")
def create_user_endpoint(req: CreateUserIn, admin: dict = Depends(require_admin)):
    role = req.role if req.role in ("user", "admin") else "user"
    auth.validate_password_strength(req.password)
    try:
        user = repo.create_user(
            username=req.username,
            password_hash=auth.hash_password(req.password),
            role=role,
        )
    except repo.AdminExistsError:
        raise HTTPException(400, "An administrator already exists — only one is allowed")
    except repo.UsernameTakenError:
        raise HTTPException(400, "Username is already taken")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "user": user}


@app.delete("/api/users/{user_id}")
def delete_user_endpoint(user_id: str, admin: dict = Depends(require_admin)):
    target = repo.get_user(user_id)
    if not target:
        raise HTTPException(404, "User not found")
    # The sole admin cannot be deleted (would lock everyone out of config)
    if target["role"] == "admin" and repo.count_admins() <= 1:
        raise HTTPException(400, "Cannot delete the only administrator")
    if user_id == admin["id"]:
        raise HTTPException(400, "You cannot delete your own account")
    repo.delete_user(user_id)
    return {"ok": True}


# ═══════════════════════════════════════════ WebSocket log ══════════════════

@app.websocket("/ws/log")
async def ws_log(ws: WebSocket):
    await ws.accept()
    q: asyncio.Queue = asyncio.Queue()
    broadcaster.subscribe(q)
    try:
        for line in broadcaster.replay(q):
            await ws.send_text(line)
        while True:
            try:
                msg = await asyncio.wait_for(q.get(), timeout=30)
                await ws.send_text(msg)
            except asyncio.TimeoutError:
                await ws.send_text("")   # keepalive ping
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        broadcaster.unsubscribe(q)


# ═══════════════════════════════════════════ Pipeline ═══════════════════════

class PipelineRequest(BaseModel):
    pasos: list[int] | None = None


@app.get("/api/pasos")
def get_pasos(_auth: dict = Depends(require_admin)):
    return [{"id": i, "nombre": n} for i, n in enumerate(pipeline.step_names())]


@app.get("/api/days")
def get_days(_auth: dict = Depends(require_login)):
    """Group all captures by date.

    Uses the captures table as the source of truth: every photo that has
    a row here appears in the gallery, no matter where it lives on disk
    (organized by YYYY/MM/DD, in /incoming, in a custom folder, etc).

    The date used to group is capture_date if present, otherwise the
    file's mtime, otherwise the file itself gets grouped under 'undated'.
    """
    from datetime import datetime as _dt

    # DB metadata: photo path → (capture_date, tags, city, gps, is_favourite)
    caps = repo.load_captures()

    # DB summaries provide zip_path for a given date if the pipeline ran
    summary_by_date: dict[str, dict] = {}
    for s in repo.load_summaries() or []:
        if s.get("fecha"):
            summary_by_date[s["fecha"]] = s

    # Group by YYYY-MM-DD
    by_date: dict[str, list[dict]] = {}
    for c in caps:
        fpath = c.get("ruta_destino") or c.get("ruta_original") or ""
        if not fpath:
            continue

        # Pick the best date we have for this photo
        date_str = ""
        cap_date = (c.get("fecha_captura") or "").strip()
        if cap_date and len(cap_date) >= 10:
            date_str = cap_date[:10]     # ISO 'YYYY-MM-DD...'
        elif c.get("mtime"):
            try:
                date_str = _dt.fromtimestamp(float(c["mtime"])).strftime("%Y-%m-%d")
            except Exception:
                pass
        if not date_str:
            date_str = "undated"

        by_date.setdefault(date_str, []).append({
            "path":    fpath,
            "size_mb": c.get("tamano_mb", 0) or 0,
        })

    days = []
    for date_str, entries in by_date.items():
        year, month, day = (date_str.split("-") + ["", "", ""])[:3] \
                           if date_str != "undated" else ("", "", "")
        # Best-effort: point 'destino' at the folder of the first photo
        first_path = entries[0]["path"] if entries else ""
        first_dir  = str(Path(first_path).parent) if first_path else ""
        extra = summary_by_date.get(date_str, {})
        days.append({
            "fecha":            date_str,
            "anio":             year,
            "mes":              month,
            "dia":              day,
            "cantidad_fotos":   len(entries),
            "tamano_total_mb":  round(sum(e["size_mb"] for e in entries), 2),
            "destino":          first_dir,
            "ruta_zip":         extra.get("ruta_zip", ""),
        })

    days.sort(key=lambda d: d["fecha"], reverse=True)
    total_photos = sum(d["cantidad_fotos"] for d in days)
    total_mb     = round(sum(d["tamano_total_mb"] for d in days), 1)
    return {
        "days":         days,
        "total_photos": total_photos,
        "total_mb":     total_mb,
        "total_days":   len(days),
    }


@app.get("/api/days/{date}/photos")
def get_day_photos(date: str, _auth: dict = Depends(require_login)):
    """Return all photos for a specific day (YYYY-MM-DD or 'undated').

    Reads from the captures table — same source as /api/days.
    """
    from datetime import datetime as _dt
    from urllib.parse import quote

    favs: set[str] = repo.favourites_set()
    photos = []

    for c in repo.load_captures():
        fpath = c.get("ruta_destino") or c.get("ruta_original") or ""
        if not fpath:
            continue

        # Same date-picking logic as /api/days
        cap_date = (c.get("fecha_captura") or "").strip()
        this_date = ""
        if cap_date and len(cap_date) >= 10:
            this_date = cap_date[:10]
        elif c.get("mtime"):
            try:
                this_date = _dt.fromtimestamp(float(c["mtime"])).strftime("%Y-%m-%d")
            except Exception:
                pass
        if not this_date:
            this_date = "undated"

        if this_date != date:
            continue

        p = Path(fpath)
        exists = p.is_file()
        photos.append({
            "id":           fpath,
            "filename":     p.name,
            "size_mb":      round(p.stat().st_size / 1048576, 2) if exists else (c.get("tamano_mb") or 0),
            "capture_date": cap_date,
            "tags":         c.get("tags", []),
            "city":         c.get("city", ""),
            "gps_lat":      c.get("gps_lat"),
            "gps_lon":      c.get("gps_lon"),
            "favourite":    fpath in favs,
            "exists":       exists,
            "url":          f"/api/photo?path={quote(fpath)}",
        })

    photos.sort(key=lambda x: x["filename"])
    return {
        "date":   date,
        "photos": photos,
        "count":  len(photos),
    }


def _allowed_bases() -> list[Path]:
    """All directories from which photos may be served.

    Includes: ORGANIZED_DIR, the configured destination, any registered
    source folders, and the incoming download directory. Resolves symlinks
    so Docker volume mounts (e.g. /data → host) work correctly.
    """
    import os

    from .config import ORGANIZED_DIR
    from .storage.folders import load_destination_config, load_saved_destination

    bases = [Path(ORGANIZED_DIR).resolve()]

    # User-configured destination
    dc = load_destination_config()
    if dc.get("tipo") == "local" and dc.get("ruta"):
        bases.append(Path(dc["ruta"]).resolve())
    ds = load_saved_destination()
    if ds:
        bases.append(Path(ds).resolve())

    # Registered source folders
    for sf in repo.load_source_folders():
        bases.append(Path(sf).resolve())

    # Incoming folder (WebDAV downloads land here)
    incoming = Path(ORGANIZED_DIR) / "incoming"
    if incoming.exists():
        bases.append(incoming.resolve())

    # PHOTOS_DIR env var (Docker volume mount root, e.g. /data)
    photos_dir = os.environ.get("PHOTOS_DIR", "")
    if photos_dir:
        bases.append(Path(photos_dir).resolve())

    # /data explicitly (Docker default mount point)
    if Path("/data").exists():
        bases.append(Path("/data").resolve())

    # Deduplicate
    seen = set()
    unique = []
    for b in bases:
        s = str(b)
        if s not in seen:
            seen.add(s)
            unique.append(b)
    return unique
    return bases


def _is_allowed(p: Path) -> bool:
    resolved_str = str(p.resolve())
    return any(resolved_str.startswith(str(b)) for b in _allowed_bases())


@app.get("/api/photo")
def serve_photo(path: str, _auth: dict = Depends(require_login)):
    """Serve a full-resolution photo file by its absolute path.
    Allows files inside ORGANIZED_DIR or the user-configured destination."""
    import mimetypes

    from fastapi.responses import FileResponse

    p = Path(path)
    if not _is_allowed(p):
        raise HTTPException(403, "Access denied — path not inside any configured destination")
    if not p.is_file():
        raise HTTPException(404, "File not found")
    mime = mimetypes.guess_type(p.name)[0] or "image/jpeg"
    return FileResponse(p, media_type=mime)


@app.get("/api/thumb")
def serve_thumbnail(path: str, size: int = 300, _auth: dict = Depends(require_login)):
    """Serve a cached JPEG thumbnail of a photo. Generates and caches it
    on first request under THUMBS_DIR/<hash>.jpg. Falls back to the full
    image if Pillow is unavailable."""
    import hashlib

    from fastapi.responses import FileResponse

    from .config import THUMBS_DIR

    p = Path(path)
    if not _is_allowed(p):
        raise HTTPException(403, "Access denied")
    if not p.is_file():
        raise HTTPException(404, "File not found")

    # Pillow required for thumbnailing
    try:
        from PIL import Image
    except ImportError:
        # Graceful fallback: serve the original
        import mimetypes
        mime = mimetypes.guess_type(p.name)[0] or "image/jpeg"
        return FileResponse(p, media_type=mime)

    size = max(64, min(size, 1024))  # clamp

    # Cache key: absolute path + size + file mtime (so edits invalidate)
    try:
        mtime = int(p.stat().st_mtime)
    except OSError:
        mtime = 0
    key = f"{p.resolve()}|{size}|{mtime}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    THUMBS_DIR.mkdir(parents=True, exist_ok=True)
    thumb_path = THUMBS_DIR / f"{digest}.jpg"

    if not thumb_path.exists():
        try:
            with Image.open(p) as img:
                rgb = img.convert("RGB")
                rgb.thumbnail((size, size), Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.LANCZOS)  # type: ignore[attr-defined]
                rgb.save(thumb_path, "JPEG", quality=82, optimize=True)
        except Exception:
            # If thumbnailing fails (corrupt file, unsupported), serve original
            import mimetypes
            mime = mimetypes.guess_type(p.name)[0] or "image/jpeg"
            return FileResponse(p, media_type=mime)

    return FileResponse(thumb_path, media_type="image/jpeg")


@app.get("/api/favourites")
def get_favourites(_auth: dict = Depends(require_login)):
    return {"favourites": repo.load_favourites()}


class BulkActionIn(BaseModel):
    paths: list[str]
    action: str  # "favourite" | "unfavourite" | "delete"


@app.post("/api/photos/bulk")
def bulk_action(req: BulkActionIn, _auth: dict = Depends(require_login)):
    """Perform a bulk action on a list of photo paths.
    action: 'favourite' | 'unfavourite' | 'delete'
    delete: moves files to a .trash/ subfolder next to the photo."""
    import shutil

    if req.action not in ("favourite", "unfavourite", "delete"):
        raise HTTPException(400, f"Unknown action: {req.action!r}")

    ok_paths = [p for p in req.paths if _is_allowed(Path(p))]
    if not ok_paths:
        raise HTTPException(403, "No allowed paths in request")

    if req.action in ("favourite", "unfavourite"):
        flag = req.action == "favourite"
        # Ensure every path exists as a capture row (upsert minimal record)
        from pathlib import Path as _Path
        for p in ok_paths:
            if not repo.get_capture_by_dest(p):
                _f = _Path(p)
                repo.upsert_captures([{
                    "id": p, "archivo": _f.name, "formato": _f.suffix.lstrip("."),
                    "tamano_mb": round(_f.stat().st_size / 1048576, 2) if _f.is_file() else 0,
                    "mtime": _f.stat().st_mtime if _f.is_file() else 0,
                    "fecha_captura": "", "ruta_original": "",
                    "ruta_destino": p, "tags": [],
                }])
        count = repo.bulk_set_favourite(ok_paths, flag)
        total = len(repo.load_favourites())
        return {"ok": True, "affected": count, "total_favourites": total, "moved": 0}

    # delete → move to .trash/ and record for restore
    moved, errors = 0, []
    for path_str in ok_paths:
        src = Path(path_str)
        if not src.is_file():
            continue
        trash = src.parent.parent.parent / ".trash"  # YYYY/MM/DD → base/.trash
        trash.mkdir(parents=True, exist_ok=True)
        dest = trash / src.name
        # Avoid name collisions in trash
        if dest.exists():
            stem, suffix = src.stem, src.suffix
            dest = trash / f"{stem}_{src.stat().st_ino}{suffix}"
        try:
            size_mb = round(src.stat().st_size / 1048576, 2)
            shutil.move(str(src), str(dest))
            # Record so it can be restored later
            repo.add_to_trash(
                original_path=str(src),
                trash_path=str(dest),
                filename=src.name,
                size_mb=size_mb,
            )
            # Remove favourite flag / capture stays but dest_path now invalid
            moved += 1
        except Exception as e:
            errors.append(str(e))
    return {"ok": True, "moved": moved, "errors": errors}


# ═══════════════════════════════════════════ Trash / Recycle bin ════════════

@app.get("/api/trash")
def get_trash(_auth: dict = Depends(require_login)):
    """List all photos currently in the trash."""
    from urllib.parse import quote
    entries = repo.list_trash()
    for e in entries:
        # thumbnail served from the trash location
        e["url"] = f"/api/photo?path={quote(e['trash_path'])}"
        e["exists"] = Path(e["trash_path"]).is_file()
    return {"trash": entries, "total": len(entries), "count": repo.trash_count()}


class TrashActionIn(BaseModel):
    ids: list[str]


@app.post("/api/trash/restore")
def restore_from_trash(req: TrashActionIn, _auth: dict = Depends(require_login)):
    """Restore trashed photos to their original location."""
    import shutil
    restored, errors = 0, []
    for entry_id in req.ids:
        entry = repo.get_trash_entry(entry_id)
        if not entry:
            continue
        src = Path(entry["trash_path"])
        dest = Path(entry["original_path"])
        if not src.is_file():
            # File already gone — clean up the stale record
            repo.remove_trash_entry(entry_id)
            errors.append(f"{entry['filename']}: file missing from trash")
            continue
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            # If something now occupies the original path, restore alongside it
            if dest.exists():
                stem, suffix = dest.stem, dest.suffix
                dest = dest.parent / f"{stem}_restored{suffix}"
            shutil.move(str(src), str(dest))
            repo.remove_trash_entry(entry_id)
            restored += 1
        except Exception as e:
            errors.append(f"{entry['filename']}: {e}")
    return {"ok": True, "restored": restored, "errors": errors}


@app.post("/api/trash/delete")
def permanently_delete(req: TrashActionIn, _auth: dict = Depends(require_login)):
    """Permanently delete trashed photos (cannot be undone)."""
    deleted, errors = 0, []
    for entry_id in req.ids:
        entry = repo.get_trash_entry(entry_id)
        if not entry:
            continue
        try:
            p = Path(entry["trash_path"])
            if p.is_file():
                p.unlink()
            repo.remove_trash_entry(entry_id)
            deleted += 1
        except Exception as e:
            errors.append(f"{entry['filename']}: {e}")
    return {"ok": True, "deleted": deleted, "errors": errors}


@app.post("/api/trash/empty")
def empty_trash(_auth: dict = Depends(require_login)):
    """Permanently delete everything in the trash."""
    entries = repo.list_trash()
    deleted = 0
    for e in entries:
        try:
            p = Path(e["trash_path"])
            if p.is_file():
                p.unlink()
            repo.remove_trash_entry(e["id"])
            deleted += 1
        except Exception:
            pass
    return {"ok": True, "deleted": deleted}


@app.post("/api/trash/purge-old")
def purge_old_trash(days: int = 30, _admin: dict = Depends(require_admin)):
    """Permanently delete trash entries older than `days` days.
    Intended to be called periodically; admin-only."""
    old = repo.trash_entries_older_than(days)
    purged = 0
    for e in old:
        try:
            p = Path(e["trash_path"])
            if p.is_file():
                p.unlink()
            repo.remove_trash_entry(e["id"])
            purged += 1
        except Exception:
            pass
    return {"ok": True, "purged": purged, "days": days}


@app.post("/api/photos/fix-dates")
def fix_capture_dates(_auth: dict = Depends(require_admin)):
    """Re-derive capture_date for every photo from its filename.

    Safe to run multiple times. upsert_captures always extracts the date
    from the filename, so re-upserting every row corrects any bad dates.
    """
    from .utils.dates import extract_date_from_filename

    caps = repo.load_captures()
    updated = 0
    skipped_no_pattern = 0
    skipped_already_good = 0

    for c in caps:
        filename = c.get("archivo") or ""
        real_date = extract_date_from_filename(filename)
        if not real_date:
            skipped_no_pattern += 1
            continue

        current = (c.get("fecha_captura") or "").strip()
        if current and current[:19] == real_date[:19]:
            skipped_already_good += 1
            continue

        # Re-upsert — the repo will set the correct date from filename
        repo.upsert_captures([c])
        updated += 1

    return {
        "ok": True,
        "total": len(caps),
        "updated": updated,
        "skipped_no_pattern": skipped_no_pattern,
        "skipped_already_good": skipped_already_good,
    }


@app.get("/api/photos/download-zip")
def download_zip(
    paths: str,
    _auth: dict = Depends(require_login),
):
    """Stream a ZIP archive containing the requested photos.

    Query param: paths — comma-separated list of absolute file paths.
    Only paths inside allowed bases are included (others silently skipped).
    The ZIP is streamed so large selections don't need to be buffered in memory.
    """
    import io
    import zipfile

    from fastapi.responses import StreamingResponse

    raw_paths = [p.strip() for p in paths.split(",") if p.strip()]
    allowed = [p for p in raw_paths if _is_allowed(Path(p)) and Path(p).is_file()]

    if not allowed:
        raise HTTPException(404, "No valid photos found in selection")

    def _iter_zip():
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED,
                             allowZip64=True) as zf:
            seen_names: dict[str, int] = {}
            for fpath in allowed:
                name = Path(fpath).name
                # Deduplicate: photo_001.jpg → photo_001_2.jpg etc.
                if name in seen_names:
                    seen_names[name] += 1
                    stem, ext = Path(name).stem, Path(name).suffix
                    name = f"{stem}_{seen_names[name]}{ext}"
                else:
                    seen_names[name] = 1
                zf.write(fpath, arcname=name)
        buf.seek(0)
        yield from buf

    filename = f"photos_{len(allowed)}.zip"
    return StreamingResponse(
        _iter_zip(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )





class FavouriteToggleIn(BaseModel):
    path: str
    favourite: bool


@app.post("/api/favourites")
def toggle_favourite(req: FavouriteToggleIn, _auth: dict = Depends(require_login)):
    """Add or remove a photo from favourites."""
    # Ensure a captures row exists for this path
    if not repo.get_capture_by_dest(req.path):
        from pathlib import Path as _Path
        _f = _Path(req.path)
        repo.upsert_captures([{
            "id": req.path, "archivo": _f.name, "formato": _f.suffix.lstrip("."),
            "tamano_mb": round(_f.stat().st_size / 1048576, 2) if _f.is_file() else 0,
            "mtime": _f.stat().st_mtime if _f.is_file() else 0,
            "fecha_captura": "", "ruta_original": "",
            "ruta_destino": req.path, "tags": [],
        }])
    repo.set_favourite(req.path, req.favourite)
    return {"ok": True}





@app.get("/api/tags")
def get_tags(_auth: dict = Depends(require_login)):
    """Return all distinct tags across all captures with their counts."""
    tags = repo.load_all_tags()
    return {"tags": tags, "total_captures": len(tags)}


@app.get("/api/cities")
def get_cities(_auth: dict = Depends(require_login)):
    """Return all distinct cities extracted from GPS EXIF metadata.
    Each entry: city name, photo count, cover photo path, coordinates."""
    cities = repo.load_all_cities()
    return {"cities": cities, "total": len(cities)}


@app.get("/api/photos/by-city/{city}")
def photos_by_city(city: str, _auth: dict = Depends(require_login)):
    """Return all photo paths that have the given city in their metadata."""
    photos = repo.photos_by_city(city)
    return {"city": city, "photos": photos, "count": len(photos)}


# ── Albums ──────────────────────────────────────────────────────────
# An album is a named collection that references existing photos by their
# absolute path. Photos are never copied or moved; a photo can belong to
# many albums. Deleting an album never deletes the underlying photos.
# Albums are persisted to the albums + album_photos tables.
#   {"id","name","cover","created","photos":[path,...]}

# Album helpers moved to repository.py


# _album_photo_dict removed — album photos built in repository.py


@app.get("/api/albums")
def get_albums(_auth: dict = Depends(require_login)):
    """List all albums with photo count and a resolved cover path."""
    albums = repo.load_albums()
    out = [{"id": a["id"], "name": a["name"], "cover": a["cover"],
             "created": a["created"], "count": a["count"]} for a in albums]
    return {"albums": out, "total": len(out)}


class AlbumCreateIn(BaseModel):
    name: str


@app.post("/api/albums")
def create_album(req: AlbumCreateIn, _auth: dict = Depends(require_login)):
    """Create a new empty album. Returns the created album with its id."""
    import uuid
    from datetime import datetime

    name = (req.name or "").strip()
    if not name:
        raise HTTPException(400, "Album name cannot be empty")

    album = repo.create_album(
        album_id=f"alb_{uuid.uuid4().hex[:8]}",
        name=name,
        created_at=datetime.now().isoformat(timespec="seconds"),
    )
    return {"ok": True, "album": album}


class AlbumRenameIn(BaseModel):
    name: str | None = None
    cover: str | None = None


@app.patch("/api/albums/{album_id}")
def update_album(album_id: str, req: AlbumRenameIn, _auth: dict = Depends(require_login)):
    """Rename an album and/or set its cover photo."""
    album = repo.get_album(album_id)
    if album is None:
        raise HTTPException(404, "Album not found")

    if req.name is not None:
        new_name = req.name.strip()
        if not new_name:
            raise HTTPException(400, "Album name cannot be empty")
        repo.update_album_name(album_id, new_name)
        album["name"] = new_name
    if req.cover is not None:
        if req.cover and req.cover not in (album.get("photos") or []):
            raise HTTPException(400, "Cover must be a photo in this album")
        repo.update_album_cover(album_id, req.cover or None)
        album["cover"] = req.cover or None

    album = repo.get_album(album_id)
    if not album:
        raise HTTPException(404, "Album not found")
    return {"ok": True, "album": {**album, "count": album["count"]}}


@app.delete("/api/albums/{album_id}")
def delete_album(album_id: str, _auth: dict = Depends(require_login)):
    """Delete an album. The underlying photos are never touched."""
    deleted = repo.delete_album(album_id)
    if not deleted:
        raise HTTPException(404, "Album not found")
    remaining = repo.load_albums()
    return {"ok": True, "total": len(remaining)}


class AlbumPhotosIn(BaseModel):
    paths: list[str]
    action: str  # "add" | "remove"


@app.post("/api/albums/{album_id}/photos")
def album_photos(album_id: str, req: AlbumPhotosIn, _auth: dict = Depends(require_login)):
    """Add or remove photos in an album by path. action: 'add' | 'remove'."""
    if req.action not in ("add", "remove"):
        raise HTTPException(400, f"Unknown action: {req.action!r}")

    if not repo.get_album(album_id):
        raise HTTPException(404, "Album not found")

    if req.action == "add":
        allowed = [p for p in req.paths if _is_allowed(Path(p))]
        count = repo.album_add_photos(album_id, allowed)
    else:
        count = repo.album_remove_photos(album_id, req.paths)

    return {"ok": True, "count": count}


@app.get("/api/albums/{album_id}")
def get_album(album_id: str, _auth: dict = Depends(require_login)):
    """Return the photos in an album, in the same shape as day photos."""
    album = repo.get_album(album_id)
    if album is None:
        raise HTTPException(404, "Album not found")

    from urllib.parse import quote
    favs = repo.favourites_set()
    meta_by_dest = {m.get("ruta_destino"): m for m in repo.load_captures() if m.get("ruta_destino")}

    photos = []
    for fpath in (album.get("photos") or []):
        path_obj = Path(fpath)
        exists = path_obj.is_file()
        meta = meta_by_dest.get(fpath, {})
        photos.append({
            "id":           fpath,
            "filename":     path_obj.name,
            "size_mb":      round(path_obj.stat().st_size / 1048576, 2) if exists else 0,
            "capture_date": meta.get("fecha_captura", ""),
            "tags":         meta.get("tags", []),
            "city":         meta.get("city", ""),
            "gps_lat":      meta.get("gps_lat"),
            "gps_lon":      meta.get("gps_lon"),
            "favourite":    fpath in favs,
            "exists":       exists,
            "url":          f"/api/photo?path={quote(fpath)}",
        })
    return {
        "id":      album["id"],
        "name":    album.get("name", "Untitled"),
        "created": album.get("created", ""),
        "count":   len(photos),
        "photos":  photos,
    }


@app.get("/api/pipeline/estado")
def pipeline_estado(_auth: dict = Depends(require_admin)):
    return {"corriendo": pipeline.is_running()}


@app.post("/api/pipeline/ejecutar")
def ejecutar_pipeline(req: PipelineRequest, _auth: dict = Depends(require_admin)):
    try:
        names = pipeline.run(req.pasos)
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return {"ok": True, "pasos": names}


# ═══════════════════════════════════════════ SSH ════════════════════════════

class SSHConnectionIn(BaseModel):
    alias: str
    host: str
    puerto: int = 22
    usuario: str
    ruta_remota: str
    ruta_remota_destino: str = ""
    clave_privada: str = ""
    rol: str = "origen"


@app.get("/api/ssh")
def listar_ssh(_auth: dict = Depends(require_admin)):
    connections = ssh_connection.load_ssh_connections()
    # No exponer la ruta de la clave privada en la respuesta de la API
    return [
        {k: v for k, v in c.items() if k != "clave_privada"}
        | {"tiene_clave": bool(c.get("clave_privada"))}
        for c in connections
    ]


@app.get("/api/ssh/roles")
def get_roles_ssh(_auth: dict = Depends(require_admin)):
    """Devuelve los roles válidos y sus reglas, para que la UI los renderice
    sin hardcodear ninguna regla en JS."""
    return {
        "roles": ssh_connection.VALID_ROLES,
        "requiere_ruta_destino": ["destino", "ambos"],
        "ruta_destino_obligatoria": ["ambos"],
        "descripcion": {
            "origen":  "El pipeline escanea este servidor en busca de capturas.",
            "destino": "Lo organizado se sube a este servidor.",
            "ambos":   "Origen Y destino. Requiere rutas distintas para evitar bucles.",
        },
    }


@app.post("/api/ssh")
def guardar_ssh(datos: SSHConnectionIn, _auth: dict = Depends(require_admin)):
    # Si el cliente envía clave_privada vacía, preservar la que ya existía
    clave = datos.clave_privada
    if not clave:
        existentes = ssh_connection.load_ssh_connections()
        prev = next((c for c in existentes if c["alias"] == datos.alias), None)
        if prev:
            clave = prev.get("clave_privada", "")
    try:
        ssh_connection.add_or_update_ssh_connection(
            alias=datos.alias, host=datos.host, puerto=datos.puerto,
            usuario=datos.usuario, ruta_remota=datos.ruta_remota,
            clave_privada=clave, rol=datos.rol,
            ruta_remota_destino=datos.ruta_remota_destino,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.delete("/api/ssh/{alias}")
def eliminar_ssh(alias: str, _auth: dict = Depends(require_admin)):
    ssh_connection.remove_ssh_connection(alias)
    return {"ok": True}


# ═══════════════════════════════════════════ WebDAV ═════════════════════════

class ConnectionWebDAVIn(BaseModel):
    letra: str
    ip: str
    puerto: str = "8080"
    alias: str = ""


@app.get("/api/webdav")
def listar_webdav(_auth: dict = Depends(require_admin)):
    return [
        {**c, "montada": connection.is_mounted(c["letra"])}
        for c in connection.load_connections()
    ]


@app.get("/api/webdav/letras")
def letras_disponibles(_auth: dict = Depends(require_admin)):
    """Letras de unidad disponibles (D:-Z:). El JS las usa para el <select>,
    sin hardcodear el rango en el cliente."""
    usadas = {c["letra"] for c in connection.load_connections()}
    return {
        "todas": connection.AVAILABLE_DRIVE_LETTERS,
        "libres": [d for d in connection.AVAILABLE_DRIVE_LETTERS if d not in usadas],
    }


@app.post("/api/webdav/connect")
async def connect_webdav(datos: ConnectionWebDAVIn, _auth: dict = Depends(require_admin)):
    loop = asyncio.get_event_loop()
    exito, mensaje = await loop.run_in_executor(
        _net_executor,
        lambda: connection.mount(datos.letra, datos.ip, datos.puerto),
    )
    if exito:
        connection.add_or_update_connection(
            datos.letra, datos.ip, datos.puerto, datos.alias or datos.letra
        )
    return {"ok": exito, "mensaje": mensaje}


@app.post("/api/webdav/disconnect/{letra}")
async def disconnect_webdav(letra: str, _auth: dict = Depends(require_admin)):
    loop = asyncio.get_event_loop()
    exito, mensaje = await loop.run_in_executor(
        _net_executor,
        lambda: connection.unmount(letra),
    )
    if exito:
        connection.remove_connection(letra)
    return {"ok": exito, "mensaje": mensaje}


class WebDAVScanIn(BaseModel):
    ip: str
    port: str = "8080"
    dest_folder: str = ""   # where to save downloads; defaults to ORGANIZED_DIR/incoming


@app.post("/api/webdav/scan")
def webdav_scan(req: WebDAVScanIn, _auth: dict = Depends(require_admin)):
    """List all photos available on a phone WebDAV server (no download yet).
    Works on any OS — uses direct HTTP, no 'net use' needed."""
    from .storage.webdav_downloader import DEFAULT_REMOTE_PATHS, list_remote_files
    all_files = []
    seen: set[str] = set()
    for rpath in DEFAULT_REMOTE_PATHS:
        found = list_remote_files(req.ip, req.port, rpath)
        for f in found:
            if f.name not in seen:
                all_files.append({"name": f.name, "size": f.size, "path": f.href})
                seen.add(f.name)
    return {"ok": True, "count": len(all_files), "files": all_files}


@app.post("/api/webdav/download")
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

    from .config import ORGANIZED_DIR
    from .storage.webdav_downloader import (
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
            import traceback
            traceback.print_exc()
            _webdav_job["error"] = str(e)
            broadcaster.emit(f"❌ Download failed: {e}\n")
        finally:
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


def _parse_webdav_modified(raw: str) -> str:
    """Parse a WebDAV Last-Modified header like 'Mon, 01 Jan 2024 00:00:00 GMT'
    into an ISO date. Returns '' on failure."""
    if not raw:
        return ""
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(raw)
        return dt.isoformat(timespec="seconds") if dt else ""
    except Exception:
        return ""


# Job state (single global; only one WebDAV download at a time)
_webdav_job: dict = {"running": False, "done": False, "error": None,
                     "total": 0, "downloaded": 0, "registered": 0, "skipped": 0,
                     "started_at": None, "finished_at": None,
                     "dest": "", "current_file": ""}




@app.get("/api/webdav/download-status")
def webdav_download_status(_auth: dict = Depends(require_admin)):
    """Poll this to know how the background download is going."""
    return dict(_webdav_job)


# ═══════════════════════════════════════════ Carpetas ═══════════════════════

class AnadirCarpetaIn(BaseModel):
    carpeta: str


class QuitarCarpetaIn(BaseModel):
    carpeta: str


class DestinoIn(BaseModel):
    tipo: str       # "local" | "ssh"
    ruta: str = ""
    alias: str = ""


@app.get("/api/carpetas")
def get_carpetas(_auth: dict = Depends(require_admin)):
    """Estado completo de carpetas: origen + destino + servidores SSH
    disponibles como destino. La UI renderiza todo a partir de esto,
    sin estado propio en JS."""
    return {
        "origen": [str(c) for c in load_saved_folders()],
        "destino": load_destination_config(),
        "servidores_ssh_destino": [
            {"alias": c["alias"], "host": c["host"]}
            for c in ssh_connection.load_ssh_connections()
            if c["rol"] in ("destino", "ambos")
        ],
    }


@app.post("/api/carpetas/origen/anadir")
def anadir_carpeta(datos: AnadirCarpetaIn, _auth: dict = Depends(require_admin)):
    carpeta = datos.carpeta.strip()
    if not carpeta:
        raise HTTPException(400, "La carpeta no puede estar vacía.")
    actuales = load_saved_folders()
    if Path(carpeta) not in actuales:
        actuales.append(Path(carpeta))
        save_folders(actuales)
    return {"ok": True, "origen": [str(c) for c in actuales]}


@app.post("/api/carpetas/origen/quitar")
def quitar_carpeta(datos: QuitarCarpetaIn, _auth: dict = Depends(require_admin)):
    actuales = [c for c in load_saved_folders() if str(c) != datos.carpeta]
    save_folders(actuales)
    return {"ok": True, "origen": [str(c) for c in actuales]}


@app.post("/api/carpetas/destino")
def set_destino(datos: DestinoIn, _auth: dict = Depends(require_admin)):
    if datos.tipo == "local":
        if not datos.ruta:
            raise HTTPException(400, "Falta la ruta para destino local.")
        save_destination(datos.ruta)
    elif datos.tipo == "ssh":
        if not datos.alias:
            raise HTTPException(400, "Falta el alias del servidor SSH.")
        c = ssh_connection.get_connection(datos.alias)
        if c is None:
            raise HTTPException(404, f"No existe ninguna conexión SSH con alias '{datos.alias}'.")
        if c["rol"] not in ("destino", "ambos"):
            raise HTTPException(400,
                f"El servidor '{datos.alias}' tiene rol '{c['rol']}': "
                "para usarlo como destino debe tener rol 'destino' o 'ambos'.")
        save_ssh_destination(datos.alias)
    else:
        raise HTTPException(400, "tipo debe ser 'local' o 'ssh'.")
    return {"ok": True, "destino": load_destination_config()}


@app.post("/api/carpetas/destino/quitar")
def quitar_destino(_auth: dict = Depends(require_admin)):
    save_destination("")
    return {"ok": True, "destino": load_destination_config()}


# ═══════════════════════════════════════════ Setup wizard ═══════════════════

@app.get("/api/diag")
def diagnostic(_admin: dict = Depends(require_admin)):
    """Diagnostic endpoint — quick overview of what's in the database.
    Useful for verifying that ingest is actually landing in the tables."""
    from .db import get_engine
    engine = get_engine()
    return {
        "db_dialect": engine.dialect.name,
        "db_url":     str(engine.url).replace(engine.url.password or "", "***"),
        "counts": {
            "captures":            len(repo.load_captures()),
            "day_summaries":       len(repo.load_summaries()),
            "source_folders":      len(repo.load_source_folders()),
            "ssh_connections":     len(repo.load_ssh_connections()),
            "webdav_connections":  len(repo.load_webdav_connections()),
            "albums":              len(repo.load_albums()),
            "trash":               repo.trash_count(),
            "users":               repo.user_count(),
        },
        "destination": repo.load_destination_config(),
    }


@app.get("/api/setup-status")
def setup_status():
    """Returns which essential configuration steps are complete.
    Used by the first-run wizard in the frontend."""
    from .storage import ssh_repo
    from .storage.connection import load_connections
    from .storage.folders import load_destination_config

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


# ═══════════════════════════════════════════ UI HTML ════════════════════════

@app.get("/", response_class=HTMLResponse)
def ui():
    return _HTML


# ──────────────────────────── lanzador de fondo ─────────────────────────────

_server_thread: threading.Thread | None = None
WEB_PORT = 8765


def iniciar_servidor_web(host: str = "127.0.0.1", port: int = WEB_PORT) -> None:
    global _server_thread
    if _server_thread and _server_thread.is_alive():
        return
    cfg = uvicorn.Config(app, host=host, port=port, log_level="warning", loop="asyncio")
    server = uvicorn.Server(cfg)

    def _run():
        asyncio.run(server.serve())

    _server_thread = threading.Thread(target=_run, daemon=True, name="photos-web")
    _server_thread.start()
    print(f"🌐 Interfaz web disponible en  http://localhost:{port}")


# ──────────────────────────── HTML inline ───────────────────────────────────
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
