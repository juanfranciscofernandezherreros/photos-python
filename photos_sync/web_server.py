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
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime as _dt
from pathlib import Path
from typing import Any
from urllib.parse import quote

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
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
from .observability import (
    PIPELINE_DURATION,
    PIPELINE_LAST_RUN_SUCCESS,
    PIPELINE_LAST_RUN_TIMESTAMP,
    PIPELINE_RUNNING,
    PIPELINE_RUNS,
    PIPELINE_STEP_DURATION,
    configure_observability,
    log_event,
    start_metrics_endpoint,
    stop_metrics_endpoint,
)
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
            sys.stdout = _BroadcastIO(self._broadcaster, orig_out)
            sys.stderr = _BroadcastIO(self._broadcaster, orig_err)
            run_started = time.perf_counter()
            run_status = "success"
            PIPELINE_RUNNING.set(1)
            log_event("pipeline_started", steps=[name for name, _ in selected])
            try:
                with prevent_sleep():
                    for name, fn in selected:
                        step_started = time.perf_counter()
                        step_status = "success"
                        self._broadcaster.emit(f"\n{'='*55}\n⏳ STARTING: {name}\n{'='*55}\n")
                        log_event("pipeline_step_started", step=name)
                        try:
                            fn()
                        except Exception:
                            step_status = "error"
                            raise
                        finally:
                            step_duration = time.perf_counter() - step_started
                            PIPELINE_STEP_DURATION.labels(step=name, status=step_status).observe(
                                step_duration
                            )
                            log_event(
                                "pipeline_step_finished",
                                level="error" if step_status == "error" else "info",
                                step=name,
                                status=step_status,
                                duration_seconds=round(step_duration, 3),
                            )
                self._broadcaster.emit("\n✅ Pipeline finished successfully.\n")
            except Exception:
                run_status = "error"
                self._broadcaster.emit("\n❌ ERROR:\n" + traceback.format_exc())
            finally:
                run_duration = time.perf_counter() - run_started
                PIPELINE_RUNS.labels(status=run_status).inc()
                PIPELINE_DURATION.labels(status=run_status).observe(run_duration)
                PIPELINE_LAST_RUN_SUCCESS.set(1 if run_status == "success" else 0)
                PIPELINE_LAST_RUN_TIMESTAMP.set(time.time())
                PIPELINE_RUNNING.set(0)
                log_event(
                    "pipeline_finished",
                    level="error" if run_status == "error" else "info",
                    status=run_status,
                    duration_seconds=round(run_duration, 3),
                )
                sys.stdout = orig_out
                sys.stderr = orig_err
                self._running = False

        threading.Thread(target=_run_thread, daemon=True, name="pipeline").start()
        return [name for name, _ in selected]


# ──────────────────────────── I/O redirect ──────────────────────────────────

class _BroadcastIO(io.TextIOBase):
    """Forward pipeline output both to the UI and the container log."""
    def __init__(self, broadcaster: LogBroadcaster, mirror: io.TextIOBase | None = None) -> None:
        self._broadcaster = broadcaster
        self._mirror = mirror

    def write(self, s: str) -> int:
        if s:
            self._broadcaster.emit(s)
            if self._mirror is not None:
                self._mirror.write(s)
        return len(s)

    def flush(self) -> None:
        if self._mirror is not None:
            self._mirror.flush()


# ──────────────────────────── Singletons ────────────────────────────────────

broadcaster = LogBroadcaster()
pipeline    = PipelineManager(broadcaster)
_net_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="net-use")

# ──────────────────────────── FastAPI app ───────────────────────────────────

@asynccontextmanager
async def _lifespan(app: FastAPI):
    init_db()  # create tables if they don't exist
    metrics_server = start_metrics_endpoint()
    try:
        yield
    finally:
        stop_metrics_endpoint(metrics_server)

app = FastAPI(title="Photos Sync Web", lifespan=_lifespan)
configure_observability(app)

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




















# ── User management (admin only) ─────────────────────────────────────────────










# ═══════════════════════════════════════════ WebSocket log ══════════════════




# ═══════════════════════════════════════════ Pipeline ═══════════════════════

class PipelineRequest(BaseModel):
    pasos: list[int] | None = None











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











class BulkActionIn(BaseModel):
    paths: list[str]
    action: str  # "favourite" | "unfavourite" | "delete"





# ═══════════════════════════════════════════ Trash / Recycle bin ════════════




class TrashActionIn(BaseModel):
    ids: list[str]























class FavouriteToggleIn(BaseModel):
    path: str
    favourite: bool













# ── Albums ──────────────────────────────────────────────────────────
# An album is a named collection that references existing photos by their
# absolute path. Photos are never copied or moved; a photo can belong to
# many albums. Deleting an album never deletes the underlying photos.
# Albums are persisted to the albums + album_photos tables.
#   {"id","name","cover","created","photos":[path,...]}

# Album helpers moved to repository.py


# _album_photo_dict removed — album photos built in repository.py





class AlbumCreateIn(BaseModel):
    name: str





class AlbumRenameIn(BaseModel):
    name: str | None = None
    cover: str | None = None








class AlbumPhotosIn(BaseModel):
    paths: list[str]
    action: str  # "add" | "remove"














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














# ═══════════════════════════════════════════ WebDAV ═════════════════════════

class ConnectionWebDAVIn(BaseModel):
    letra: str
    ip: str
    puerto: str = "8080"
    alias: str = ""














class WebDAVScanIn(BaseModel):
    ip: str
    port: str = "8080"
    dest_folder: str = ""   # where to save downloads; defaults to ORGANIZED_DIR/incoming








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







# ═══════════════════════════════════════════ Carpetas ═══════════════════════

class AnadirCarpetaIn(BaseModel):
    carpeta: str


class QuitarCarpetaIn(BaseModel):
    carpeta: str


class DestinoIn(BaseModel):
    tipo: str       # "local" | "ssh"
    ruta: str = ""
    alias: str = ""
























# ═══════════════════════════════════════════ UI HTML ════════════════════════




# ──────────────────────────── lanzador de fondo ─────────────────────────────

_server_thread: threading.Thread | None = None
WEB_PORT = 8765


def iniciar_servidor_web(host: str = "127.0.0.1", port: int = WEB_PORT) -> None:
    global _server_thread
    if _server_thread and _server_thread.is_alive():
        return
    cfg = uvicorn.Config(
        app, host=host, port=port, log_level="warning", loop="asyncio", access_log=False
    )
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




# Each route lives in a dedicated module. Importing and including routers here
# keeps ``photos_sync.web_server:app`` as the stable public entry point.
_ENDPOINT_MODULES = (
    "health",
    "get_lockouts",
    "unlock_user",
    "auth_status",
    "setup_admin",
    "login",
    "logout",
    "auth_me",
    "change_password",
    "get_users",
    "create_user_endpoint",
    "delete_user_endpoint",
    "ws_log",
    "get_pasos",
    "get_days",
    "get_day_photos",
    "get_photos",
    "serve_photo",
    "serve_thumbnail",
    "get_favourites",
    "bulk_action",
    "get_trash",
    "restore_from_trash",
    "permanently_delete",
    "empty_trash",
    "purge_old_trash",
    "fix_capture_dates",
    "download_zip",
    "toggle_favourite",
    "get_tags",
    "get_albums",
    "create_album",
    "update_album",
    "delete_album",
    "album_photos",
    "get_album",
    "pipeline_estado",
    "ejecutar_pipeline",
    "listar_ssh",
    "get_roles_ssh",
    "guardar_ssh",
    "eliminar_ssh",
    "listar_webdav",
    "letras_disponibles",
    "connect_webdav",
    "disconnect_webdav",
    "webdav_scan",
    "webdav_download",
    "webdav_download_status",
    "get_carpetas",
    "anadir_carpeta",
    "quitar_carpeta",
    "set_destino",
    "quitar_destino",
    "diagnostic",
    "ui",
)

for _endpoint_module_name in _ENDPOINT_MODULES:
    _endpoint_module = __import__(
        f"{__package__}.endpoints.{_endpoint_module_name}",
        fromlist=["router"],
    )
    app.include_router(_endpoint_module.router)


if __name__ == "__main__":
    import uvicorn as _uv
    _uv.run(app, host="127.0.0.1", port=WEB_PORT)
