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
    Carga la ruta de destino LOCAL guardada en el archivo JSON.
    Devuelve None si el archivo no existe, está corrupto, o si el destino
    configurado es en realidad un servidor SSH (ver cargar_destino_config()).

    Se mantiene por compatibilidad: organizar.py y comprimir.py la usan tal
    cual para decidir la carpeta local donde se organiza/comprime siempre
    (incluso si luego, además, se sube esa misma carpeta a un servidor SSH).
    """
    config = cargar_destino_config()
    if config.get("tipo") == "local":
        return config.get("ruta")
    return None


def guardar_destino(ruta: str) -> None:
    """
    Guarda la ruta de destino LOCAL seleccionada en un archivo JSON.
    """
    datos = {"tipo": "local", "ruta": ruta}
    try:
        with open(ARCHIVO_DESTINO_JSON, 'w', encoding='utf-8') as f:
            json.dump(datos, f, indent=4, ensure_ascii=False)
    except OSError as e:
        print(f"❌ Error al guardar el destino: {e}")


def cargar_destino_config() -> dict:
    """
    Carga la configuración de destino completa: {"tipo": "local", "ruta": ...}
    o {"tipo": "ssh", "alias": ...} si el destino elegido es un servidor
    Linux por SSH (ver ssh_conexion.py). Devuelve {} si no hay nada
    configurado o el archivo está corrupto.

    Nota: por compatibilidad con versiones anteriores del proyecto, un
    fichero antiguo con el formato {"destino": "ruta"} se sigue leyendo
    correctamente como destino local.
    """
    archivo = Path(ARCHIVO_DESTINO_JSON)
    if not archivo.exists():
        return {}

    try:
        with open(archivo, 'r', encoding='utf-8') as f:
            datos = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}

    if not isinstance(datos, dict):
        return {}

    if datos.get("tipo") in ("local", "ssh"):
        return datos
    if "destino" in datos:  # formato antiguo, antes de añadir soporte SSH
        return {"tipo": "local", "ruta": datos["destino"]}
    return {}


def guardar_destino_ssh(alias: str) -> None:
    """
    Configura el destino como un servidor Linux ya guardado en
    ssh_conexion.py (identificado por su alias), en vez de una carpeta
    local. La organización local (organizar.py) sigue haciéndose en la
    carpeta por defecto/local que ya hubiera configurada; el paso extra
    'subir_ssh.py' es quien envía lo organizado a este servidor.
    """
    datos = {"tipo": "ssh", "alias": alias}
    try:
        with open(ARCHIVO_DESTINO_JSON, 'w', encoding='utf-8') as f:
            json.dump(datos, f, indent=4, ensure_ascii=False)
    except OSError as e:
        print(f"❌ Error al guardar el destino SSH: {e}")