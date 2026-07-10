import json
from pathlib import Path

from .config import ARCHIVO_CARPETAS_SELECCIONADAS, RUTAS_SCREENSHOTS_ORIGEN


def cargar_carpetas_guardadas() -> list[Path]:
    archivo = Path(ARCHIVO_CARPETAS_SELECCIONADAS)
    if not archivo.exists():
        return list(RUTAS_SCREENSHOTS_ORIGEN)

    try:
        with open(archivo, 'r', encoding='utf-8') as f:
            rutas_guardadas: list[str] = json.load(f)
        if not rutas_guardadas:
            return list(RUTAS_SCREENSHOTS_ORIGEN)
        return [Path(r) for r in rutas_guardadas]
    except (json.JSONDecodeError, TypeError):
        print(f"⚠️ '{ARCHIVO_CARPETAS_SELECCIONADAS}' is corrupt, using default folders from config.py.")
        return list(RUTAS_SCREENSHOTS_ORIGEN)


def guardar_carpetas(carpetas: list[Path]) -> None:
    with open(ARCHIVO_CARPETAS_SELECCIONADAS, 'w', encoding='utf-8') as f:
        json.dump([str(c) for c in carpetas], f, indent=4, ensure_ascii=False)
