"""
Source-folder and destination config — delegates to repository (PostgreSQL).
Preserves the same public API consumed by the pipeline and the GUI.
"""
from __future__ import annotations
from pathlib import Path
from .. import repository as repo
from . import connection as connection_mod


def load_saved_folders() -> list[Path]:
    paths = repo.load_source_folders()
    if not paths:
        return connection_mod.default_source_paths()
    return [Path(p) for p in paths]


def save_folders(carpetas: list[Path]) -> None:
    repo.save_source_folders([str(c) for c in carpetas])


def load_saved_destination() -> str | None:
    return repo.load_saved_destination()


def save_destination(ruta: str) -> None:
    repo.save_destination_local(ruta)


def load_destination_config() -> dict:
    return repo.load_destination_config()


def save_ssh_destination(alias: str) -> None:
    repo.save_destination_ssh(alias)
