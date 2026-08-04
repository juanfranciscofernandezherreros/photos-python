"""
WebDAV connection management — delegates to repository (PostgreSQL).
Preserves all public functions used by the rest of the project.
"""
from __future__ import annotations

import platform
import subprocess
from pathlib import Path
from typing import TypedDict

from .. import repository as repo

AVAILABLE_DRIVE_LETTERS: list[str] = [
    f"{chr(c)}:" for c in range(ord('D'), ord('Z') + 1)
]


class Connection(TypedDict):
    letra: str
    ip: str
    puerto: str
    alias: str


def load_connections() -> list[dict]:
    return repo.load_webdav_connections()


def save_connections(conexiones: list[Connection]) -> None:
    # Full replace via repo
    from sqlalchemy import delete

    from ..db import get_engine, t_webdav
    with get_engine().begin() as conn:
        conn.execute(delete(t_webdav))
    for c in conexiones:
        repo.add_or_update_webdav(c["letra"], c["ip"], c["puerto"], c.get("alias", ""))


def add_or_update_connection(letra: str, ip: str, puerto: str, alias: str = "") -> list[dict]:
    return repo.add_or_update_webdav(letra, ip, puerto, alias)


def remove_connection(letra: str) -> list[dict]:
    return repo.remove_webdav(letra)


def is_mounted(letra: str) -> bool:
    letra_norm = letra if letra.endswith("\\") else f"{letra}\\"
    return Path(letra_norm).exists()


def _run_net_use(comando: list[str], timeout: int) -> subprocess.CompletedProcess:
    flags = 0
    if platform.system() == "Windows":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(
        " ".join(comando), shell=True,
        capture_output=True, text=True,
        timeout=timeout, creationflags=flags,
    )


def mount(letra: str, ip: str, puerto: str) -> tuple[bool, str]:
    if platform.system() != "Windows":
        return False, "Mounting with 'net use' only works on Windows."
    comando = ["net", "use", letra, f"http://{ip}:{puerto}"]
    try:
        r = _run_net_use(comando, timeout=20)
    except subprocess.TimeoutExpired:
        return False, f"⏱️ Connection timed out for {ip}:{puerto}."
    except OSError as e:
        return False, f"Could not execute 'net use': {e}"
    out = (r.stdout + r.stderr).strip()
    return (r.returncode == 0), out or f"net use returned {r.returncode}"


def unmount(letra: str) -> tuple[bool, str]:
    if platform.system() != "Windows":
        return False, "Unmounting with 'net use' only works on Windows."
    comando = ["net", "use", letra, "/delete", "/y"]
    try:
        r = _run_net_use(comando, timeout=15)
    except OSError as e:
        return False, f"Could not execute 'net use': {e}"
    out = (r.stdout + r.stderr).strip()
    return (r.returncode == 0), out or f"net use /delete returned {r.returncode}"


def default_source_paths() -> list[Path]:
    rutas: list[Path] = []
    for c in load_connections():
        letra = c["letra"]
        rutas.append(Path(rf"{letra}\Pictures\Screenshots"))
        rutas.append(Path(rf"{letra}\DCIM\Screenshots"))
    return rutas
