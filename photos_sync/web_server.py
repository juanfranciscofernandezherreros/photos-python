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
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from . import connection, download, organize, compress, summary, ssh_connection, upload_ssh
from .folders import (load_saved_folders, save_folders,
                       load_destination_config, save_destination, save_ssh_destination)
from .keep_awake import prevent_sleep

# ──────────────────────────── Pipeline steps ────────────────────────────────

PASOS: list[tuple[str, Any]] = [
    ("Download metadata",   download.export_metadata_json),
    ("Organize by date",    organize.organize_captures_by_date),
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
    yield

app = FastAPI(title="Photos Sync Web", lifespan=_lifespan)


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
def get_pasos():
    return [{"id": i, "nombre": n} for i, n in enumerate(pipeline.step_names())]


@app.get("/api/days")
def get_days():
    """Returns the daily summary from the organized destination folder."""
    from .config import DAILY_SUMMARY_JSON, ORGANIZED_DIR
    from .json_io import read_json
    days = read_json(DAILY_SUMMARY_JSON, default=[])
    if not isinstance(days, list):
        days = []
    org = Path(ORGANIZED_DIR)
    if org.exists() and not days:
        for year_dir in sorted(org.iterdir()):
            if not year_dir.is_dir() or year_dir.name == "Comprimidos":
                continue
            for month_dir in sorted(year_dir.iterdir()):
                if not month_dir.is_dir():
                    continue
                for day_dir in sorted(month_dir.iterdir()):
                    if not day_dir.is_dir():
                        continue
                    files = [f for f in day_dir.iterdir() if f.is_file()]
                    if files:
                        days.append({
                            "fecha": f"{year_dir.name}-{month_dir.name}-{day_dir.name}",
                            "anio": year_dir.name,
                            "mes": month_dir.name,
                            "dia": day_dir.name,
                            "cantidad_fotos": len(files),
                            "tamano_total_mb": round(sum(f.stat().st_size for f in files) / 1048576, 2),
                            "destino": str(day_dir),
                        })
    days.sort(key=lambda d: d.get("fecha", ""), reverse=True)
    total_photos = sum(d.get("cantidad_fotos", 0) for d in days)
    total_mb = round(sum(d.get("tamano_total_mb", 0) for d in days), 1)
    return {"days": days, "total_photos": total_photos, "total_mb": total_mb, "total_days": len(days)}


@app.get("/api/pipeline/estado")
def pipeline_estado():
    return {"corriendo": pipeline.is_running()}


@app.post("/api/pipeline/ejecutar")
def ejecutar_pipeline(req: PipelineRequest):
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
def listar_ssh():
    connections = ssh_connection.load_ssh_connections()
    # No exponer la ruta de la clave privada en la respuesta de la API
    return [
        {k: v for k, v in c.items() if k != "clave_privada"}
        | {"tiene_clave": bool(c.get("clave_privada"))}
        for c in connections
    ]


@app.get("/api/ssh/roles")
def get_roles_ssh():
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
def guardar_ssh(datos: SSHConnectionIn):
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
def eliminar_ssh(alias: str):
    ssh_connection.remove_ssh_connection(alias)
    return {"ok": True}


# ═══════════════════════════════════════════ WebDAV ═════════════════════════

class ConnectionWebDAVIn(BaseModel):
    letra: str
    ip: str
    puerto: str = "8080"
    alias: str = ""


@app.get("/api/webdav")
def listar_webdav():
    return [
        {**c, "montada": connection.is_mounted(c["letra"])}
        for c in connection.load_connections()
    ]


@app.get("/api/webdav/letras")
def letras_disponibles():
    """Letras de unidad disponibles (D:-Z:). El JS las usa para el <select>,
    sin hardcodear el rango en el cliente."""
    usadas = {c["letra"] for c in connection.load_connections()}
    return {
        "todas": connection.AVAILABLE_DRIVE_LETTERS,
        "libres": [l for l in connection.AVAILABLE_DRIVE_LETTERS if l not in usadas],
    }


@app.post("/api/webdav/connect")
async def connect_webdav(datos: ConnectionWebDAVIn):
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
async def disconnect_webdav(letra: str):
    loop = asyncio.get_event_loop()
    exito, mensaje = await loop.run_in_executor(
        _net_executor,
        lambda: connection.unmount(letra),
    )
    if exito:
        connection.remove_connection(letra)
    return {"ok": exito, "mensaje": mensaje}


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
def get_carpetas():
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
def anadir_carpeta(datos: AnadirCarpetaIn):
    carpeta = datos.carpeta.strip()
    if not carpeta:
        raise HTTPException(400, "La carpeta no puede estar vacía.")
    actuales = load_saved_folders()
    if Path(carpeta) not in actuales:
        actuales.append(Path(carpeta))
        save_folders(actuales)
    return {"ok": True, "origen": [str(c) for c in actuales]}


@app.post("/api/carpetas/origen/quitar")
def quitar_carpeta(datos: QuitarCarpetaIn):
    actuales = [c for c in load_saved_folders() if str(c) != datos.carpeta]
    save_folders(actuales)
    return {"ok": True, "origen": [str(c) for c in actuales]}


@app.post("/api/carpetas/destino")
def set_destino(datos: DestinoIn):
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
def quitar_destino():
    save_destination("")
    return {"ok": True, "destino": load_destination_config()}


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