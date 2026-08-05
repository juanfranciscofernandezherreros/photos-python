"""
WebDAV connection management — delegates to repository (PostgreSQL).
Preserves all public functions used by the rest of the project.
"""
from __future__ import annotations

import ipaddress
import locale
import os
import platform
import re
import subprocess
from pathlib import Path
from typing import TypedDict

from .. import repository as repo

AVAILABLE_DRIVE_LETTERS: list[str] = [
    f"{chr(c)}:" for c in range(ord('D'), ord('Z') + 1)
]

_DRIVE_RE = re.compile(r"^[D-Z]:$", re.IGNORECASE)


class Connection(TypedDict):
    letra: str
    ip: str
    puerto: str
    alias: str


def load_connections() -> list[dict]:
    return repo.load_webdav_connections()


def add_or_update_connection(letra: str, ip: str, puerto: str, alias: str = "") -> list[dict]:
    return repo.add_or_update_webdav(letra, ip, puerto, alias)


def remove_connection(letra: str) -> list[dict]:
    return repo.remove_webdav(letra)


def is_mounted(letra: str) -> bool:
    letra_norm = letra if letra.endswith("\\") else f"{letra}\\"
    return Path(letra_norm).exists()


def normalize_drive_letter(value: str) -> str:
    drive = (value or "").strip().upper()
    if not _DRIVE_RE.fullmatch(drive):
        raise ValueError("Drive letter must be between D: and Z:")
    return drive


def normalize_webdav_host(value: str) -> str:
    host = (value or "").strip()
    try:
        return str(ipaddress.ip_address(host))
    except ValueError as exc:
        raise ValueError("WebDAV host must be a valid IPv4 or IPv6 address") from exc


def normalize_port(value: str | int) -> str:
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("WebDAV port must be an integer") from exc
    if not 1 <= port <= 65535:
        raise ValueError("WebDAV port must be between 1 and 65535")
    return str(port)


def _net_executable() -> Path:
    system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    return system_root / "System32" / "net.exe"


def _run_net_use(comando: list[str], timeout: int) -> subprocess.CompletedProcess:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    args = [str(_net_executable()), *comando[1:]]
    return subprocess.run(
        args,
        shell=False,
        capture_output=True,
        text=True,
        encoding=locale.getpreferredencoding(False),
        errors="replace",
        timeout=timeout,
        creationflags=flags,
    )


def mount(letra: str, ip: str, puerto: str) -> tuple[bool, str]:
    if platform.system() != "Windows":
        return False, "Mounting with 'net use' only works on Windows."
    try:
        drive = normalize_drive_letter(letra)
        host = normalize_webdav_host(ip)
        port = normalize_port(puerto)
    except ValueError as exc:
        return False, str(exc)
    url_host = f"[{host}]" if ":" in host else host
    comando = ["net", "use", drive, f"http://{url_host}:{port}"]
    try:
        r = _run_net_use(comando, timeout=20)
    except subprocess.TimeoutExpired:
        return False, f"⏱️ Connection timed out for {ip}:{puerto}."
    except OSError as e:
        return False, f"Could not execute 'net use': {e}"
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    return (r.returncode == 0), out or f"net use returned {r.returncode}"


def unmount(letra: str) -> tuple[bool, str]:
    if platform.system() != "Windows":
        return False, "Unmounting with 'net use' only works on Windows."
    try:
        drive = normalize_drive_letter(letra)
    except ValueError as exc:
        return False, str(exc)
    comando = ["net", "use", drive, "/delete", "/y"]
    try:
        r = _run_net_use(comando, timeout=15)
    except OSError as e:
        return False, f"Could not execute 'net use': {e}"
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    return (r.returncode == 0), out or f"net use /delete returned {r.returncode}"


def default_source_paths() -> list[Path]:
    rutas: list[Path] = []
    for c in load_connections():
        letra = c["letra"]
        rutas.append(Path(rf"{letra}\Pictures\Screenshots"))
        rutas.append(Path(rf"{letra}\DCIM\Screenshots"))
    return rutas
