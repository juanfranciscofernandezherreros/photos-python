"""
Thin helpers for reading/writing JSON state files.

Every module in the project (carpetas, conexion, ssh_conexion, download,
comprimir, resumen) had its own copy of the same pattern:

    archivo = Path(SOME_CONSTANT)
    if not archivo.exists(): return default
    try:
        with open(archivo, 'r', encoding='utf-8') as f:
            data = json.load(f)
        ...
    except (json.JSONDecodeError, OSError):
        return default

This module centralises that into two functions so the pattern lives in
one place and callers stay focused on their own logic.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_json(path: str | Path, default: Any = None) -> Any:
    """Read and parse a JSON file. Return *default* if the file does not
    exist, is empty, or contains invalid JSON."""
    archivo = Path(path)
    if not archivo.exists():
        return default
    try:
        with open(archivo, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError, ValueError):
        return default


def write_json(path: str | Path, data: Any) -> None:
    """Write *data* as pretty-printed JSON.  Creates parent directories
    if they don't exist yet."""
    archivo = Path(path)
    archivo.parent.mkdir(parents=True, exist_ok=True)
    with open(archivo, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
