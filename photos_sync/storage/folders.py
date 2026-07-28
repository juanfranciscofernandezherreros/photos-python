"""
Lectura y escritura de la selección de carpetas a escanear.

Deliberadamente sin ningún import de PyQt6: este módulo lo usa tanto la
ventana gráfica (selector_carpetas.py) como el propio pipeline
(download.py). Así, ejecutar `photos-sync --todo` en un servidor sin
interfaz gráfica nunca necesita cargar PyQt6.
"""
from pathlib import Path

from ..config import SELECTED_FOLDERS_JSON, DESTINATION_JSON
from ..json_io import read_json, write_json
from ..storage import connection as connection


def load_saved_folders() -> list[Path]:
    """Returns the folders to scan: those explicitly saved by the GUI
    selector if they exist, otherwise the typical screenshot folders from each
    captures from each connected phone (see connection.py)."""
    rutas_guardadas = read_json(SELECTED_FOLDERS_JSON)
    if not rutas_guardadas or not isinstance(rutas_guardadas, list):
        return connection.default_source_paths()
    return [Path(r) for r in rutas_guardadas]


def save_folders(carpetas: list[Path]) -> None:
    write_json(SELECTED_FOLDERS_JSON, [str(c) for c in carpetas])


def load_saved_destination() -> str | None:
    """
    Load the saved LOCAL destination path from the JSON file.
    Returns None if the file does not exist, is corrupt, or if the
    destination is actually an SSH server (see load_destination_config()).
    """
    config = load_destination_config()
    if config.get("tipo") == "local":
        return config.get("ruta")
    return None


def save_destination(ruta: str) -> None:
    """Save the selected LOCAL destination path."""
    try:
        write_json(DESTINATION_JSON, {"tipo": "local", "ruta": ruta})
    except OSError as e:
        print(f"❌ Error saving destination: {e}")


def load_destination_config() -> dict:
    """
    Load the full destination configuration: {"tipo": "local", "ruta": ...}
    or {"tipo": "ssh", "alias": ...} if the chosen destination is a
    Linux server via SSH (see ssh_connection.py). Returns {} if nothing
    is configured or the file is corrupt.

    Note: for backwards compatibility, an old file with the format
    {"destino": "ruta"} is still read correctly as a local destination.
    """
    datos = read_json(DESTINATION_JSON, default={})
    if not isinstance(datos, dict):
        return {}
    if datos.get("tipo") in ("local", "ssh"):
        return datos
    if "destino" in datos:  # legacy format, before SSH support was added
        return {"tipo": "local", "ruta": datos["destino"]}
    return {}


def save_ssh_destination(alias: str) -> None:
    """
    Set the destination to a Linux server already saved in
    ssh_connection.py (identified by its alias), instead of a local folder.
    """
    try:
        write_json(DESTINATION_JSON, {"tipo": "ssh", "alias": alias})
    except OSError as e:
        print(f"❌ Error saving SSH destination: {e}")