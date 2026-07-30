"""
WebDAV connection management (one per phone).

Stores multiple connections (drive letter + IP + port), one per phone.
The rest of the project reads from here instead of hardcoding a drive letter.

Deliberately free of PyQt6 imports so headless mode works without the GUI.
"""
from __future__ import annotations

import json
import platform
import subprocess
from pathlib import Path
from typing import Any, TypedDict

from ..config import WEBDAV_CONNECTIONS_JSON
from ..json_io import read_json, write_json

# Valid drive letters for a Windows network drive. A/B (legacy floppy)
# and C (usually system disk) are excluded.
AVAILABLE_DRIVE_LETTERS: list[str] = [f"{chr(codigo)}:" for codigo in range(ord('D'), ord('Z') + 1)]


class Connection(TypedDict):
    letra: str
    ip: str
    puerto: str
    alias: str  # free-form name to identify the phone, e.g. "Nothing Phone"


def load_connections() -> list[Connection]:
    """All saved connections (one per phone), whether currently mounted or not."""
    datos = read_json(WEBDAV_CONNECTIONS_JSON, default=[])
    return datos if isinstance(datos, list) else []


def save_connections(conexiones: list[Connection]) -> None:
    write_json(WEBDAV_CONNECTIONS_JSON, conexiones)


def add_or_update_connection(letra: str, ip: str, puerto: str, alias: str = "") -> list[Connection]:
    """Guarda (o actualiza si la letra ya existía) una conexión y devuelve
    la lista completa actualizada."""
    conexiones = load_connections()
    nueva: Connection = {"letra": letra, "ip": ip, "puerto": puerto, "alias": alias or letra}
    conexiones = [c for c in conexiones if c["letra"] != letra]
    conexiones.append(nueva)
    save_connections(conexiones)
    return conexiones


def remove_connection(letra: str) -> list[Connection]:
    conexiones = [c for c in load_connections() if c["letra"] != letra]
    save_connections(conexiones)
    return conexiones


def is_mounted(letra: str) -> bool:
    """Comprueba si la letra de unidad indicada existe ahora mismo en el
    sistema (esté o no en nuestra lista de conexiones guardadas)."""
    letra_normalizada = letra if letra.endswith("\\") else f"{letra}\\"
    return Path(letra_normalizada).exists()


def _run_net_use(comando: list[str], timeout: int) -> subprocess.CompletedProcess:
    """Ejecuta un comando `net use` garantizando que hereda la sesión
    interactiva del usuario de Windows.

    Problemas que resuelve:
    - Sin `shell=True`, cuando el proceso padre es un hilo de uvicorn/FastAPI
      el comando se lanza en una sesión de servicio distinta y no ve las
      unidades de red del usuario actual → falla con "Acceso denegado".
    - Sin `CREATE_NO_WINDOW`, aparece una ventana de cmd negra momentánea.
    - Explicit timeout to avoid blocking the event loop if the phone is unresponsive.
    """
    flags = 0
    if platform.system() == "Windows":
        flags = subprocess.CREATE_NO_WINDOW  # evita ventana cmd visible
    return subprocess.run(
        " ".join(comando),   # shell=True requiere string, no lista
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=flags,
    )


def mount(letra: str, ip: str, puerto: str) -> tuple[bool, str]:
    """Ejecuta `net use LETRA: http://ip:puerto`. Equivalente exacto al
    comando manual que antes había que escribir en una terminal aparte."""
    if platform.system() != "Windows":
        return False, ("Mounting network drives with 'net use' only works on Windows. "
                        "This command cannot be executed on this system.")

    comando = ["net", "use", letra, f"http://{ip}:{puerto}"]
    try:
        resultado = _run_net_use(comando, timeout=20)
    except subprocess.TimeoutExpired:
        return False, (f"⏱️ Connection timed out for {ip}:{puerto}. "
                        "Make sure the phone is on the same WiFi network and that the "
                        "WebDAV server is still running in the app.")
    except OSError as e:
        return False, f"Could not execute 'net use': {e}"

    salida = (resultado.stdout + resultado.stderr).strip()
    if resultado.returncode == 0:
        return True, salida or f"{letra} successfully connected to {ip}:{puerto}."
    return False, salida or f"'net use' returned error code {resultado.returncode}."


def unmount(letra: str) -> tuple[bool, str]:
    """Ejecuta `net use LETRA: /delete /y`."""
    if platform.system() != "Windows":
        return False, "Unmounting network drives with 'net use' only works on Windows."

    comando = ["net", "use", letra, "/delete", "/y"]
    try:
        resultado = _run_net_use(comando, timeout=15)
    except OSError as e:
        return False, f"Could not execute 'net use': {e}"

    salida = (resultado.stdout + resultado.stderr).strip()
    if resultado.returncode == 0:
        return True, salida or f"{letra} disconnected."
    return False, salida or f"'net use /delete' returned error code {resultado.returncode}."


def default_source_paths() -> list[Path]:
    """Typical Android screenshot subfolders, one pair
    per connected phone. Replaces the old fixed list based on a single
    Z: drive — now generated dynamically based on how many connections
    are saved."""
    rutas: list[Path] = []
    for conexion in load_connections():
        letra = conexion["letra"]
        rutas.append(Path(rf"{letra}\Pictures\Screenshots"))
        rutas.append(Path(rf"{letra}\DCIM\Screenshots"))
    return rutas
