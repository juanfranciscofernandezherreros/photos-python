"""
Lectura y escritura de la selección de carpetas a escanear.

Deliberadamente sin ningún import de tkinter: este módulo lo usa tanto la
ventana gráfica (selector_carpetas.py) como el propio pipeline
(descargar.py). Así, ejecutar `photos-sync --todo` en un servidor sin
interfaz gráfica nunca necesita cargar tkinter.
"""
import json
from pathlib import Path

from .config import ARCHIVO_CARPETAS_SELECCIONADAS, RUTAS_SCREENSHOTS_ORIGEN


def cargar_carpetas_guardadas() -> list[Path]:
    """Devuelve las carpetas a escanear: las guardadas por el selector
    gráfico si existen, o si no, las de config.py por defecto."""
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
        print(f"⚠️ '{ARCHIVO_CARPETAS_SELECCIONADAS}' está corrupto, usando las carpetas por defecto de config.py.")
        return list(RUTAS_SCREENSHOTS_ORIGEN)


def guardar_carpetas(carpetas: list[Path]) -> None:
    """Persiste la selección en la carpeta de trabajo actual (el cwd)."""
    with open(ARCHIVO_CARPETAS_SELECCIONADAS, 'w', encoding='utf-8') as f:
        json.dump([str(c) for c in carpetas], f, indent=4, ensure_ascii=False)
