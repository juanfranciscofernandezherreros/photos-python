"""
Lectura y escritura de la selección de carpetas a escanear.

Deliberadamente sin ningún import de PyQt6: este módulo lo usa tanto la
ventana gráfica (selector_carpetas.py) como el propio pipeline
(descargar.py). Así, ejecutar `photos-sync --todo` en un servidor sin
interfaz gráfica nunca necesita cargar PyQt6.
"""
import json
from pathlib import Path

from .config import ARCHIVO_CARPETAS_SELECCIONADAS, ARCHIVO_DESTINO_JSON
from . import conexion


def cargar_carpetas_guardadas() -> list[Path]:
    """Devuelve las carpetas a escanear: las guardadas explícitamente por
    el selector gráfico si existen, o si no, las carpetas típicas de
    capturas de cada móvil que tengas conectado (ver conexion.py)."""
    archivo = Path(ARCHIVO_CARPETAS_SELECCIONADAS)
    if not archivo.exists():
        return conexion.rutas_origen_por_defecto()

    try:
        with open(archivo, 'r', encoding='utf-8') as f:
            rutas_guardadas: list[str] = json.load(f)
        if not rutas_guardadas:
            return conexion.rutas_origen_por_defecto()
        return [Path(r) for r in rutas_guardadas]
    except (json.JSONDecodeError, TypeError):
        print(f"⚠️ '{ARCHIVO_CARPETAS_SELECCIONADAS}' está corrupto, usando las carpetas por defecto de cada móvil conectado.")
        return conexion.rutas_origen_por_defecto()


def guardar_carpetas(carpetas: list[Path]) -> None:
    """Persiste la selección en la carpeta de trabajo actual (el cwd)."""
    with open(ARCHIVO_CARPETAS_SELECCIONADAS, 'w', encoding='utf-8') as f:
        json.dump([str(c) for c in carpetas], f, indent=4, ensure_ascii=False)


def cargar_destino_guardado() -> str | None:
    """
    Carga la ruta de destino guardada en el archivo JSON.
    Devuelve None si el archivo no existe o está corrupto.
    """
    archivo = Path(ARCHIVO_DESTINO_JSON)
    if not archivo.exists():
        return None
        
    try:
        with open(archivo, 'r', encoding='utf-8') as f:
            datos = json.load(f)
            return datos.get("destino")
    except (json.JSONDecodeError, KeyError, OSError):
        return None

def guardar_destino(ruta: str) -> None:
    """
    Guarda la ruta de destino seleccionada en un archivo JSON.
    """
    datos = {"destino": ruta}
    try:
        with open(ARCHIVO_DESTINO_JSON, 'w', encoding='utf-8') as f:
            json.dump(datos, f, indent=4, ensure_ascii=False)
    except OSError as e:
        print(f"❌ Error al guardar el destino: {e}")