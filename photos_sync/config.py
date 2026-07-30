from __future__ import annotations

from pathlib import Path

BASE_DIR: Path = Path.home() / "PhotosSync"
ORGANIZED_DIR: Path = BASE_DIR / "screenshots_agrupados"
ZIPS_DIR: Path = ORGANIZED_DIR / "Comprimidos"

# ── State and configuration files ──
# All live under BASE_DIR so they do not depend on the cwd.
_DATA_DIR: Path = BASE_DIR / "data"
METADATA_JSON: str        = str(_DATA_DIR / "metadatos_screenshots.json")
SELECTED_FOLDERS_JSON: str = str(_DATA_DIR / "carpetas_screenshots.json")
DESTINATION_JSON: str          = str(_DATA_DIR / "destino_guardado.json")
DAILY_SUMMARY_JSON: str          = str(_DATA_DIR / "resumen_por_dia.json")
ORCHESTRATOR_LOG: str       = str(_DATA_DIR / "orquestador.log")
WEBDAV_CONNECTIONS_JSON: str       = str(_DATA_DIR / "conexiones_webdav.json")
SSH_CONNECTIONS_JSON: str   = str(_DATA_DIR / "conexiones_ssh.json")
FAVOURITES_JSON: str        = str(_DATA_DIR / "favourites.json")

# Create the data directory if it does not exist
_DATA_DIR.mkdir(parents=True, exist_ok=True)

VALID_EXTENSIONS: list[str] = ['.png', '.jpg', '.jpeg', '.webp']
COPY_THREADS: int = 8
DELETE_ORIGINALS_AFTER_COMPRESS: bool = False