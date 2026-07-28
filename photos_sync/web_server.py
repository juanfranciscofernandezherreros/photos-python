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

_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Photos Sync</title>
<script src="https://cdn.tailwindcss.com"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<script>
tailwind.config = {
  theme: {
    extend: {
      fontFamily: { sans: ['Inter', 'system-ui', 'sans-serif'], mono: ['JetBrains Mono', 'monospace'] },
      colors: {
        sky: { 50:'#f0f9ff',100:'#e0f2fe',200:'#bae6fd',300:'#7dd3fc',400:'#38bdf8',500:'#0ea5e9',600:'#0284c7',700:'#0369a1',800:'#075985',900:'#0c4a6e' }
      }
    }
  }
}
</script>
<style>
  body { font-family: 'Inter', system-ui, sans-serif; }
  .fade-in { animation: fadeIn .3s ease }
  @keyframes fadeIn { from{opacity:0;transform:translateY(6px)} to{opacity:1;transform:translateY(0)} }
  @keyframes spin { to{transform:rotate(360deg)} }
  .spinner { animation: spin .6s linear infinite }
  #log-box::-webkit-scrollbar { width:5px }
  #log-box::-webkit-scrollbar-track { background:transparent }
  #log-box::-webkit-scrollbar-thumb { background:#cbd5e1; border-radius:3px }
  [data-section] { display:none } [data-section].active { display:block }
</style>
</head>
<body class="bg-white text-slate-800 min-h-screen">
<div class="flex min-h-screen">

  <!-- ─── Sidebar ─── -->
  <aside class="w-56 bg-sky-50 border-r border-sky-100 flex flex-col flex-shrink-0 sticky top-0 h-screen overflow-y-auto">
    <div class="px-5 py-5 border-b border-sky-100">
      <div class="flex items-center gap-2.5">
        <div class="w-8 h-8 rounded-lg bg-sky-500 flex items-center justify-center">
          <svg class="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>
        </div>
        <div>
          <div class="text-sm font-bold text-slate-800">Photos Sync</div>
          <div class="text-[10px] font-semibold text-sky-500 uppercase tracking-wider">Dashboard</div>
        </div>
      </div>
    </div>
    <div id="srv-status" class="mx-3 mt-3 px-3 py-1.5 rounded-md text-[11px] font-semibold text-center bg-sky-100 text-sky-600 border border-sky-200 transition-all">Connecting…</div>
    <nav class="flex flex-col gap-0.5 px-3 mt-4">
      <div class="text-[10px] font-bold text-slate-400 uppercase tracking-widest px-2 pb-2">Navigation</div>
      <button class="nav-btn active" onclick="tab('gallery',this)">
        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
        Gallery
      </button>
      <button class="nav-btn" onclick="tab('pipeline',this)">
        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8"><polygon points="5 3 19 12 5 21 5 3"/></svg>
        Pipeline
      </button>
      <button class="nav-btn" onclick="tab('ssh',this)">
        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="M7 15l3-3-3-3"/><line x1="14" y1="15" x2="17" y2="15"/></svg>
        SSH
      </button>
      <button class="nav-btn" onclick="tab('webdav',this)">
        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8"><path d="M12 2a10 10 0 100 20 10 10 0 000-20z"/><path d="M2 12h20"/></svg>
        WebDAV
      </button>
      <button class="nav-btn" onclick="tab('folders',this)">
        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/></svg>
        Folders
      </button>
    </nav>
    <div class="mt-auto px-4 py-4 text-[10px] text-slate-400">v0.1.0</div>
  </aside>

  <!-- ─── Main ─── -->
  <main class="flex-1 min-w-0 p-6 md:p-8 max-w-5xl">

    <!-- ═══ GALLERY (Landing) ═══ -->
    <section data-section="gallery" class="active fade-in">
      <div class="flex items-center justify-between mb-6">
        <div>
          <h1 class="text-2xl font-extrabold text-slate-900 tracking-tight">Gallery</h1>
          <p class="text-sm text-slate-500 mt-0.5">Organized photos by day</p>
        </div>
        <button onclick="loadDays()" class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-sky-600 bg-sky-50 border border-sky-200 rounded-lg hover:bg-sky-100 transition">
          <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
          Refresh
        </button>
      </div>
      <!-- Stats row -->
      <div class="grid grid-cols-3 gap-3 mb-6" id="stats-row">
        <div class="bg-sky-50 border border-sky-100 rounded-xl px-4 py-3 text-center">
          <div class="text-2xl font-bold text-sky-600" id="stat-days">—</div>
          <div class="text-[11px] font-medium text-slate-500 uppercase tracking-wider mt-0.5">Days</div>
        </div>
        <div class="bg-sky-50 border border-sky-100 rounded-xl px-4 py-3 text-center">
          <div class="text-2xl font-bold text-sky-600" id="stat-photos">—</div>
          <div class="text-[11px] font-medium text-slate-500 uppercase tracking-wider mt-0.5">Photos</div>
        </div>
        <div class="bg-sky-50 border border-sky-100 rounded-xl px-4 py-3 text-center">
          <div class="text-2xl font-bold text-sky-600" id="stat-size">—</div>
          <div class="text-[11px] font-medium text-slate-500 uppercase tracking-wider mt-0.5">MB Total</div>
        </div>
      </div>
      <!-- Day cards grid -->
      <div id="days-grid" class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        <div class="col-span-full text-center py-16 text-slate-400">
          <svg class="w-10 h-10 mx-auto mb-2 text-sky-200" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>
          Loading…
        </div>
      </div>
    </section>

    <!-- ═══ PIPELINE ═══ -->
    <section data-section="pipeline" class="fade-in">
      <h1 class="text-2xl font-extrabold text-slate-900 tracking-tight">Pipeline</h1>
      <p class="text-sm text-slate-500 mt-0.5 mb-5">Select steps and run the sync.</p>
      <div class="bg-white border border-slate-200 rounded-xl p-5 shadow-sm mb-4">
        <div id="paso-checks" class="grid grid-cols-2 sm:grid-cols-3 gap-2 mb-4"></div>
        <div class="flex gap-2">
          <button class="px-4 py-2 text-sm font-semibold text-white bg-sky-500 rounded-lg hover:bg-sky-600 transition inline-flex items-center gap-1.5 disabled:opacity-40" id="btn-run-sel" onclick="runPipeline(false)">
            <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            Run selected
          </button>
          <button class="px-4 py-2 text-sm font-semibold text-sky-700 bg-sky-100 border border-sky-200 rounded-lg hover:bg-sky-200 transition inline-flex items-center gap-1.5 disabled:opacity-40" id="btn-run-all" onclick="runPipeline(true)">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" viewBox="0 0 24 24"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
            Run ALL
          </button>
        </div>
      </div>
      <div class="flex items-center gap-2.5 mb-3 px-1">
        <div id="spinner" class="hidden w-4 h-4 border-2 border-slate-200 border-t-sky-500 rounded-full spinner"></div>
        <span id="pipeline-status" class="text-sm text-slate-500 font-medium">Ready.</span>
      </div>
      <div id="log-box" class="bg-slate-50 border border-slate-200 rounded-xl p-4 h-80 overflow-y-auto font-mono text-xs leading-relaxed text-slate-600 whitespace-pre-wrap break-all" style="scrollbar-width:thin;scrollbar-color:#cbd5e1 transparent"></div>
    </section>

    <!-- ═══ SSH ═══ -->
    <section data-section="ssh" class="fade-in">
      <h1 class="text-2xl font-extrabold text-slate-900 tracking-tight">SSH Connections</h1>
      <p class="text-sm text-slate-500 mt-0.5 mb-5">Configure remote servers for source and destination.</p>
      <div class="bg-white border border-slate-200 rounded-xl p-5 shadow-sm mb-4">
        <h3 class="text-sm font-semibold text-slate-700 mb-3">New connection</h3>
        <div class="grid grid-cols-6 gap-3">
          <div class="col-span-2"><label class="lbl">Alias</label><input id="ssh-alias" placeholder="Home NAS" class="inp"></div>
          <div class="col-span-3"><label class="lbl">Host / IP</label><input id="ssh-host" placeholder="192.168.1.50" class="inp"></div>
          <div class="col-span-1"><label class="lbl">Port</label><input id="ssh-puerto" value="22" type="number" class="inp"></div>
        </div>
        <div class="grid grid-cols-2 gap-3 mt-2">
          <div><label class="lbl">User</label><input id="ssh-usuario" placeholder="juan" class="inp"></div>
          <div><label class="lbl">Remote path (source)</label><input id="ssh-ruta" placeholder="/home/juan/fotos" class="inp"></div>
        </div>
        <div class="grid grid-cols-2 gap-3 mt-2">
          <div>
            <label class="lbl">Remote path (dest)</label>
            <input id="ssh-ruta-dest" placeholder="only if role=ambos" disabled class="inp">
            <div class="text-[11px] text-slate-400 mt-0.5" id="ssh-ruta-dest-hint"></div>
          </div>
          <div><label class="lbl">Private key (local path)</label><input id="ssh-clave" placeholder="~/.ssh/id_rsa (optional)" class="inp"></div>
        </div>
        <div class="mt-2 w-40">
          <label class="lbl">Role</label>
          <select id="ssh-rol" onchange="onRolChange()" class="inp"></select>
          <div class="text-[11px] text-slate-400 mt-0.5" id="ssh-rol-hint"></div>
        </div>
        <div class="flex gap-2 mt-4">
          <button class="btn-primary" onclick="guardarSSH()">Save connection</button>
          <button class="btn-ghost" onclick="limpiarFormSSH()">Clear</button>
        </div>
        <div id="ssh-msg" class="msg mt-3"></div>
      </div>
      <div class="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
        <h3 class="text-sm font-semibold text-slate-700 mb-3">Saved connections</h3>
        <div class="overflow-x-auto"><table id="ssh-table" class="tbl"><thead><tr><th>Alias</th><th>Host</th><th>User</th><th>Source</th><th>Dest</th><th>Role</th><th></th></tr></thead><tbody></tbody></table></div>
      </div>
    </section>

    <!-- ═══ WEBDAV ═══ -->
    <section data-section="webdav" class="fade-in">
      <h1 class="text-2xl font-extrabold text-slate-900 tracking-tight">WebDAV Connections</h1>
      <p class="text-sm text-slate-500 mt-0.5 mb-5">Mount phone drives to access photos.</p>
      <div class="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 text-sm text-amber-700 mb-4 flex gap-2 items-start">
        <svg class="w-4 h-4 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>
        <span>Connect/disconnect via <code class="bg-amber-100 px-1 rounded text-xs">net use</code> only works on Windows. May take up to 20s if the phone is unresponsive.</span>
      </div>
      <div class="bg-white border border-slate-200 rounded-xl p-5 shadow-sm mb-4">
        <h3 class="text-sm font-semibold text-slate-700 mb-3">New connection</h3>
        <div class="grid grid-cols-6 gap-3">
          <div><label class="lbl">Drive</label><select id="wd-letra" class="inp"></select></div>
          <div class="col-span-2"><label class="lbl">Phone IP</label><input id="wd-ip" placeholder="192.168.1.133" class="inp"></div>
          <div><label class="lbl">Port</label><input id="wd-puerto" value="8080" class="inp"></div>
          <div class="col-span-2"><label class="lbl">Alias</label><input id="wd-alias" placeholder="Nothing Phone 1" class="inp"></div>
        </div>
        <div class="mt-4"><button class="btn-primary" id="btn-wd-conectar" onclick="conectarWD()">Connect drive</button></div>
        <div id="wd-msg" class="msg mt-3"></div>
      </div>
      <div class="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
        <h3 class="text-sm font-semibold text-slate-700 mb-3">Mounted drives</h3>
        <div class="overflow-x-auto"><table id="wd-table" class="tbl"><thead><tr><th>Drive</th><th>Alias</th><th>IP</th><th>Port</th><th>Status</th><th></th></tr></thead><tbody></tbody></table></div>
      </div>
    </section>

    <!-- ═══ FOLDERS ═══ -->
    <section data-section="folders" class="fade-in">
      <h1 class="text-2xl font-extrabold text-slate-900 tracking-tight">Folders</h1>
      <p class="text-sm text-slate-500 mt-0.5 mb-5">Source and destination directories.</p>
      <div class="bg-white border border-slate-200 rounded-xl p-5 shadow-sm mb-4">
        <h3 class="text-sm font-semibold text-slate-700 mb-1">Source folders</h3>
        <p class="text-[11px] text-slate-400 mb-3">Directories scanned for captures. Click × to remove.</p>
        <div id="carpetas-origen-list" class="flex flex-wrap gap-2"></div>
        <div class="flex gap-2 mt-3">
          <input id="nueva-carpeta" placeholder="/mnt/nothing/DCIM  or  Z:\DCIM" class="inp flex-1" onkeydown="if(event.key==='Enter') addCarpeta()">
          <button class="btn-primary whitespace-nowrap" onclick="addCarpeta()">Add folder</button>
        </div>
        <div id="carpetas-msg" class="msg mt-3"></div>
      </div>
      <div class="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
        <h3 class="text-sm font-semibold text-slate-700 mb-1">Destination</h3>
        <p class="text-[11px] text-slate-400 mb-3">Where organized files are stored.</p>
        <div class="grid grid-cols-3 gap-3 mb-3">
          <div>
            <label class="lbl">Type</label>
            <select id="dest-tipo" onchange="destTipoChange()" class="inp"><option value="local">Local</option><option value="ssh">SSH Server</option></select>
          </div>
          <div class="col-span-2" id="dest-local-wrap"><label class="lbl">Local path</label><input id="dest-ruta" placeholder="/home/user/photos_organized" class="inp"></div>
          <div class="col-span-2" id="dest-ssh-wrap" style="display:none"><label class="lbl">SSH Server</label><select id="dest-ssh-alias" class="inp"><option value="">— loading… —</option></select><div class="text-[11px] text-slate-400 mt-0.5" id="dest-ssh-hint"></div></div>
        </div>
        <div class="flex gap-2">
          <button class="btn-primary" onclick="guardarDestino()">Save destination</button>
          <button class="px-3 py-1.5 text-xs font-semibold text-red-500 bg-red-50 border border-red-200 rounded-lg hover:bg-red-100 transition" onclick="quitarDestino()">Remove destination</button>
        </div>
        <div id="destino-msg" class="msg mt-3"></div>
      </div>
    </section>

  </main>
</div>

<style>
  .nav-btn { @apply flex items-center gap-2.5 px-3 py-2 rounded-lg text-[13px] font-medium text-slate-500 transition-all w-full text-left border-none bg-transparent cursor-pointer; }
  .nav-btn:hover { @apply bg-sky-100/60 text-slate-700; }
  .nav-btn.active { @apply bg-sky-500 text-white shadow-sm; }
  .nav-btn.active svg { @apply opacity-100; }
  .nav-btn svg { @apply opacity-50; }
  .lbl { @apply block text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-1; }
  .inp { @apply w-full bg-slate-50 border border-slate-200 text-slate-800 text-sm px-3 py-2 rounded-lg outline-none transition; }
  .inp:focus { @apply border-sky-400 ring-2 ring-sky-100; }
  .inp:disabled { @apply opacity-40 cursor-not-allowed; }
  .btn-primary { @apply px-4 py-2 text-xs font-semibold text-white bg-sky-500 rounded-lg hover:bg-sky-600 transition inline-flex items-center gap-1.5; }
  .btn-ghost { @apply px-4 py-2 text-xs font-semibold text-slate-500 bg-white border border-slate-200 rounded-lg hover:border-slate-300 transition; }
  .tbl { @apply w-full text-sm; }
  .tbl th { @apply text-left text-[10px] font-bold text-slate-400 uppercase tracking-wider px-3 py-2 border-b border-slate-200; }
  .tbl td { @apply px-3 py-2.5 border-b border-slate-100 align-middle; }
  .tbl tr:hover td { @apply bg-sky-50/50; }
  .msg { @apply text-xs font-medium px-3 py-2 rounded-lg hidden; }
  .msg-ok { @apply block bg-emerald-50 text-emerald-600 border border-emerald-200; }
  .msg-err { @apply block bg-red-50 text-red-500 border border-red-200; }
  .tag { @apply inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider; }
  .tag-origen { @apply bg-sky-100 text-sky-600; }
  .tag-destino { @apply bg-emerald-100 text-emerald-600; }
  .tag-ambos { @apply bg-amber-100 text-amber-600; }
  .day-card { @apply bg-white border border-slate-200 rounded-xl p-4 hover:border-sky-300 hover:shadow-md transition cursor-default; }
  @media(max-width:768px){
    .flex.min-h-screen{flex-direction:column}
    aside{width:100%;height:auto;position:static;border-right:none;border-bottom:1px solid #e0f2fe}
    aside nav{display:flex;gap:4px;flex-wrap:wrap;padding:8px 12px}
    aside .nav-btn{padding:6px 10px;font-size:12px}
  }
</style>

<script>
const $ = id => document.getElementById(id);

async function api(path, opts={}) {
  const r = await fetch(path, {
    headers:{'Content-Type':'application/json'},
    ...opts,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
  return data;
}

function showMsg(id, text, ok) {
  const el = $(id);
  el.className = 'msg mt-3 ' + (ok ? 'msg-ok' : 'msg-err');
  el.textContent = text;
  el.style.display = 'block';
  setTimeout(() => { el.style.display='none'; }, 5000);
}

function tab(id, btn) {
  document.querySelectorAll('[data-section]').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  document.querySelector(`[data-section="${id}"]`).classList.add('active');
  btn.classList.add('active');
  if (id==='gallery')  loadDays();
  if (id==='ssh')      initSSH();
  if (id==='webdav')   initWebDAV();
  if (id==='folders')  initCarpetas();
}

// ─── WebSocket ──────────────────────────────────────────
const logBox = $('log-box');
let ws;
function conectarWS() {
  const proto = location.protocol==='https:'?'wss':'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws/log`);
  ws.onmessage = e => {
    if (!e.data) return;
    logBox.textContent += e.data;
    logBox.scrollTop = logBox.scrollHeight;
  };
  ws.onopen = () => {
    logBox.textContent = '';
    const s = $('srv-status');
    s.textContent = 'Online';
    s.className = 'mx-3 mt-3 px-3 py-1.5 rounded-md text-[11px] font-semibold text-center bg-emerald-50 text-emerald-600 border border-emerald-200 transition-all';
  };
  ws.onclose = () => {
    const s = $('srv-status');
    s.textContent = 'Offline';
    s.className = 'mx-3 mt-3 px-3 py-1.5 rounded-md text-[11px] font-semibold text-center bg-red-50 text-red-500 border border-red-200 transition-all';
    setTimeout(conectarWS, 3000);
  };
}
conectarWS();

// ─── Gallery (Days) ─────────────────────────────────────
const MONTH_NAMES = ['','Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

async function loadDays() {
  try {
    const data = await api('/api/days');
    $('stat-days').textContent = data.total_days;
    $('stat-photos').textContent = data.total_photos.toLocaleString();
    $('stat-size').textContent = data.total_mb.toLocaleString();
    const grid = $('days-grid');
    if (!data.days.length) {
      grid.innerHTML = `<div class="col-span-full text-center py-16 text-slate-400">
        <svg class="w-12 h-12 mx-auto mb-3 text-sky-200" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>
        <p class="font-medium">No photos organized yet</p>
        <p class="text-xs mt-1">Run the Pipeline to scan and organize your photos.</p>
      </div>`;
      return;
    }
    grid.innerHTML = '';
    data.days.forEach(d => {
      const m = parseInt(d.mes, 10);
      const div = document.createElement('div');
      div.className = 'day-card';
      div.innerHTML = `
        <div class="flex items-center justify-between mb-2">
          <span class="text-xs font-bold text-sky-500 uppercase tracking-wider">${MONTH_NAMES[m]} ${d.anio}</span>
          <span class="w-7 h-7 flex items-center justify-center rounded-full bg-sky-100 text-sky-600 text-xs font-bold">${d.cantidad_fotos}</span>
        </div>
        <div class="text-3xl font-extrabold text-slate-800 leading-none">${parseInt(d.dia,10)}</div>
        <div class="text-[11px] text-slate-400 mt-1.5">${d.tamano_total_mb} MB${d.ruta_zip ? '  ·  zipped' : ''}</div>`;
      grid.appendChild(div);
    });
  } catch(e) {
    console.error('loadDays:', e);
  }
}
loadDays();

// ─── Pipeline ───────────────────────────────────────────
async function initPipeline() {
  const pasos = await api('/api/pasos');
  const grid = $('paso-checks');
  grid.innerHTML = '';
  pasos.forEach(p => {
    const lbl = document.createElement('label');
    lbl.className = 'flex items-center gap-2 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2.5 cursor-pointer hover:border-sky-300 transition text-sm font-medium text-slate-600 select-none';
    lbl.innerHTML = `<input type="checkbox" value="${p.id}" checked class="w-4 h-4 accent-sky-500"> ${p.nombre}`;
    grid.appendChild(lbl);
  });
  pollEstado();
}
initPipeline();

let pollTimer;
async function pollEstado() {
  const { corriendo } = await api('/api/pipeline/estado');
  setPipelineUI(corriendo);
  if (corriendo) pollTimer = setTimeout(pollEstado, 1500);
}

async function runPipeline(all) {
  const checks = [...document.querySelectorAll('#paso-checks input:checked')];
  const pasos = all ? null : checks.map(c => +c.value);
  if (!all && pasos.length===0) return;
  try {
    await api('/api/pipeline/ejecutar', {method:'POST', body:{pasos}});
    setPipelineUI(true);
    pollTimer = setTimeout(pollEstado, 1500);
  } catch(e) { $('pipeline-status').textContent = e.message; }
}

function setPipelineUI(running) {
  $('spinner').classList.toggle('hidden', !running);
  $('pipeline-status').textContent = running ? 'Running pipeline…' : 'Ready.';
  $('btn-run-sel').disabled = running;
  $('btn-run-all').disabled = running;
}

// ─── SSH ────────────────────────────────────────────────
let _sshReglas = {};
async function initSSH() {
  _sshReglas = await api('/api/ssh/roles');
  const sel = $('ssh-rol'); sel.innerHTML = '';
  _sshReglas.roles.forEach(r => { const o=document.createElement('option'); o.value=r; o.textContent=r; sel.appendChild(o); });
  onRolChange(); await renderSSH();
}
async function renderSSH() {
  const lista = await api('/api/ssh');
  const tbody = document.querySelector('#ssh-table tbody'); tbody.innerHTML = '';
  if(!lista.length){ tbody.innerHTML='<tr><td colspan="7" class="text-center py-6 text-slate-400 text-sm">No SSH connections yet</td></tr>'; return; }
  lista.forEach(c => {
    const tagCls={origen:'tag-origen',destino:'tag-destino',ambos:'tag-ambos'}[c.rol]||'';
    const tr=document.createElement('tr');
    tr.innerHTML=`<td><a href="#" onclick="editSSH(${JSON.stringify(c).replace(/"/g,'&quot;')});return false" class="text-sky-600 font-medium hover:underline">${c.alias}</a></td>
      <td>${c.host}:${c.puerto}</td><td>${c.usuario}</td>
      <td class="font-mono text-xs text-slate-500">${c.ruta_remota}</td>
      <td class="font-mono text-xs text-slate-500">${c.ruta_remota_destino||'—'}</td>
      <td><span class="tag ${tagCls}">${c.rol}</span></td>
      <td><button class="text-xs text-red-400 hover:text-red-600 font-semibold" onclick="borrarSSH('${c.alias}')">Delete</button></td>`;
    tbody.appendChild(tr);
  });
}
function onRolChange() {
  const rol=$('ssh-rol').value, dest=$('ssh-ruta-dest'), r=_sshReglas;
  const hab=(r.requiere_ruta_destino||[]).includes(rol); dest.disabled=!hab;
  $('ssh-rol-hint').textContent=(r.descripcion||{})[rol]||'';
  const obl=(r.ruta_destino_obligatoria||[]).includes(rol);
  dest.placeholder=obl?'REQUIRED: different from source':'optional: empty = use source path';
  $('ssh-ruta-dest-hint').textContent=obl?'Must differ from source to avoid re-scan loops.':'';
}
function editSSH(c) {
  $('ssh-alias').value=c.alias; $('ssh-host').value=c.host; $('ssh-puerto').value=c.puerto;
  $('ssh-usuario').value=c.usuario; $('ssh-ruta').value=c.ruta_remota;
  $('ssh-ruta-dest').value=c.ruta_remota_destino||'';
  $('ssh-clave').value='';
  $('ssh-clave').placeholder=c.tiene_clave?'(key configured — leave empty to keep)':'~/.ssh/id_rsa (optional)';
  $('ssh-rol').value=c.rol; onRolChange();
  document.querySelector('[data-section="ssh"] .bg-white').scrollIntoView({behavior:'smooth'});
}
async function guardarSSH() {
  try {
    await api('/api/ssh',{method:'POST',body:{alias:$('ssh-alias').value.trim(),host:$('ssh-host').value.trim(),puerto:+$('ssh-puerto').value||22,usuario:$('ssh-usuario').value.trim(),ruta_remota:$('ssh-ruta').value.trim(),ruta_remota_destino:$('ssh-ruta-dest').value.trim(),clave_privada:$('ssh-clave').value.trim(),rol:$('ssh-rol').value}});
    showMsg('ssh-msg','Connection saved.',true); limpiarFormSSH(); renderSSH();
  } catch(e) { showMsg('ssh-msg',e.message,false); }
}
async function borrarSSH(alias) { if(!confirm('Delete "'+alias+'"?'))return; await api('/api/ssh/'+encodeURIComponent(alias),{method:'DELETE'}); renderSSH(); }
function limpiarFormSSH() { ['ssh-alias','ssh-host','ssh-usuario','ssh-ruta','ssh-ruta-dest','ssh-clave'].forEach(id=>$(id).value=''); $('ssh-puerto').value='22'; if($('ssh-rol').options.length){$('ssh-rol').selectedIndex=0;onRolChange();} }

// ─── WebDAV ─────────────────────────────────────────────
async function initWebDAV() {
  const{libres}=await api('/api/webdav/letras'); const sel=$('wd-letra'); sel.innerHTML='';
  (libres.length?libres:['Z:']).forEach(l=>{const o=document.createElement('option');o.value=l;o.textContent=l;sel.appendChild(o);});
  await renderWD();
}
async function renderWD() {
  const lista=await api('/api/webdav'); const tbody=document.querySelector('#wd-table tbody'); tbody.innerHTML='';
  if(!lista.length){tbody.innerHTML='<tr><td colspan="6" class="text-center py-6 text-slate-400 text-sm">No WebDAV drives</td></tr>';return;}
  lista.forEach(c=>{const ok=c.montada; const tr=document.createElement('tr');
    tr.innerHTML=`<td class="font-semibold">${c.letra}</td><td>${c.alias||''}</td><td class="font-mono text-xs">${c.ip}</td><td>${c.puerto}</td>
      <td><span class="inline-flex items-center gap-1.5"><span class="w-2 h-2 rounded-full ${ok?'bg-emerald-400':'bg-red-400'}"></span>${ok?'Connected':'Disconnected'}</span></td>
      <td>${ok?'<button class="text-xs text-red-400 hover:text-red-600 font-semibold" onclick="disconnectWD(\''+c.letra+'\')">Disconnect</button>':'—'}</td>`;
    tbody.appendChild(tr);
  });
}
async function conectarWD() {
  const btn=$('btn-wd-conectar'); btn.disabled=true; btn.textContent='Connecting…';
  try { const res=await api('/api/webdav/connect',{method:'POST',body:{letra:$('wd-letra').value,ip:$('wd-ip').value.trim(),puerto:$('wd-puerto').value.trim()||'8080',alias:$('wd-alias').value.trim()}}); showMsg('wd-msg',res.mensaje,res.ok); await initWebDAV();
  } catch(e){showMsg('wd-msg',e.message,false);} finally{btn.disabled=false;btn.textContent='Connect drive';}
}
async function disconnectWD(l) { const res=await api('/api/webdav/disconnect/'+encodeURIComponent(l),{method:'POST'}); showMsg('wd-msg',res.mensaje,res.ok); await initWebDAV(); }

// ─── Folders ────────────────────────────────────────────
async function initCarpetas() {
  const data=await api('/api/carpetas'); renderOrigen(data.origen); renderDestinoSSH(data.servidores_ssh_destino);
  const cfg=data.destino||{};
  if(cfg.tipo==='ssh'){$('dest-tipo').value='ssh';destTipoChange();$('dest-ssh-alias').value=cfg.alias||'';} else {$('dest-tipo').value='local';destTipoChange();$('dest-ruta').value=cfg.ruta||'';}
}
function renderOrigen(lista) {
  const c=$('carpetas-origen-list'); c.innerHTML='';
  if(!lista||!lista.length){c.innerHTML='<span class="text-xs text-slate-400">No source folders added.</span>';return;}
  lista.forEach(p=>{const d=document.createElement('div');d.className='inline-flex items-center gap-2 bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 font-mono text-xs';
    d.innerHTML=`<span>${p}</span><button class="text-red-400 hover:text-red-600 text-sm leading-none" onclick="quitarCarpeta('${p.replace(/'/g,"\\'")}',this.parentNode)">&times;</button>`;c.appendChild(d);});
}
function renderDestinoSSH(servers) {
  const sel=$('dest-ssh-alias'), prev=sel.value; sel.innerHTML='<option value="">— choose server —</option>';
  (servers||[]).forEach(s=>{const o=document.createElement('option');o.value=s.alias;o.textContent=s.alias+' ('+s.host+')';if(s.alias===prev)o.selected=true;sel.appendChild(o);});
  $('dest-ssh-hint').textContent=servers&&!servers.length?'No SSH servers with destination/ambos role. Add one in SSH tab.':'';
}
async function addCarpeta() { const v=$('nueva-carpeta').value.trim(); if(!v)return; try{const d=await api('/api/carpetas/origen/anadir',{method:'POST',body:{carpeta:v}});$('nueva-carpeta').value='';renderOrigen(d.origen);showMsg('carpetas-msg','Folder added.',true);}catch(e){showMsg('carpetas-msg',e.message,false);} }
async function quitarCarpeta(c,el) { try{await api('/api/carpetas/origen/quitar',{method:'POST',body:{carpeta:c}});el.remove();const cont=$('carpetas-origen-list');if(!cont.children.length)cont.innerHTML='<span class="text-xs text-slate-400">No source folders added.</span>';showMsg('carpetas-msg','Folder removed.',true);}catch(e){showMsg('carpetas-msg',e.message,false);} }
function destTipoChange() { $('dest-local-wrap').style.display=$('dest-tipo').value==='local'?'':'none'; $('dest-ssh-wrap').style.display=$('dest-tipo').value==='ssh'?'':'none'; }
async function guardarDestino() { const t=$('dest-tipo').value, b=t==='local'?{tipo:'local',ruta:$('dest-ruta').value.trim()}:{tipo:'ssh',alias:$('dest-ssh-alias').value}; try{await api('/api/carpetas/destino',{method:'POST',body:b});showMsg('destino-msg','Destination saved.',true);}catch(e){showMsg('destino-msg',e.message,false);} }
async function quitarDestino() { if(!confirm('Remove destination config?'))return; try{await api('/api/carpetas/destino/quitar',{method:'POST'});$('dest-ruta').value='';$('dest-ssh-alias').value='';showMsg('destino-msg','Destination removed.',true);}catch(e){showMsg('destino-msg',e.message,false);} }
</script>
</body>
</html>
"""



if __name__ == "__main__":
    import uvicorn as _uv
    _uv.run(app, host="127.0.0.1", port=WEB_PORT)