"""
Gestión de conexiones WebDAV (una por móvil).

Antes, todo el proyecto asumía una única unidad fija: Z:. Ahora se pueden
guardar varias conexiones (letra de unidad + IP + puerto), una por cada
móvil, y el resto del proyecto (carpetas.py, descargar.py, la ventana
principal...) las lee de aquí en vez de tener la letra escrita a fuego.

Deliberadamente sin ningún import de PyQt6, igual que carpetas.py: así el
modo desatendido (`photos-sync --todo`) no necesita cargar la GUI.
"""
import json
import platform
import subprocess
from pathlib import Path
from typing import Any, TypedDict

from .config import ARCHIVO_CONEXIONES_JSON

# Letras válidas para una unidad de red en Windows. Se excluyen A/B
# (disqueteras heredadas) y C (casi siempre el disco del sistema); Windows
# rechazaría igualmente intentar usarlas, pero así el desplegable no las
# ofrece para evitar líos.
LETRAS_DISPONIBLES: list[str] = [f"{chr(codigo)}:" for codigo in range(ord('D'), ord('Z') + 1)]


class Conexion(TypedDict):
    letra: str
    ip: str
    puerto: str
    alias: str  # nombre libre para identificar el móvil, ej. "Nothing Phone"


def cargar_conexiones() -> list[Conexion]:
    """Todas las conexiones guardadas (una por móvil), estén o no montadas
    ahora mismo."""
    archivo = Path(ARCHIVO_CONEXIONES_JSON)
    if not archivo.exists():
        return []
    try:
        with open(archivo, 'r', encoding='utf-8') as f:
            datos = json.load(f)
        if not isinstance(datos, list):
            return []
        return datos
    except (json.JSONDecodeError, OSError):
        return []


def guardar_conexiones(conexiones: list[Conexion]) -> None:
    with open(ARCHIVO_CONEXIONES_JSON, 'w', encoding='utf-8') as f:
        json.dump(conexiones, f, indent=4, ensure_ascii=False)


def anadir_o_actualizar_conexion(letra: str, ip: str, puerto: str, alias: str = "") -> list[Conexion]:
    """Guarda (o actualiza si la letra ya existía) una conexión y devuelve
    la lista completa actualizada."""
    conexiones = cargar_conexiones()
    nueva: Conexion = {"letra": letra, "ip": ip, "puerto": puerto, "alias": alias or letra}
    conexiones = [c for c in conexiones if c["letra"] != letra]
    conexiones.append(nueva)
    guardar_conexiones(conexiones)
    return conexiones


def quitar_conexion(letra: str) -> list[Conexion]:
    conexiones = [c for c in cargar_conexiones() if c["letra"] != letra]
    guardar_conexiones(conexiones)
    return conexiones


def esta_montada(letra: str) -> bool:
    """Comprueba si la letra de unidad indicada existe ahora mismo en el
    sistema (esté o no en nuestra lista de conexiones guardadas)."""
    letra_normalizada = letra if letra.endswith("\\") else f"{letra}\\"
    return Path(letra_normalizada).exists()


def montar(letra: str, ip: str, puerto: str) -> tuple[bool, str]:
    """Ejecuta `net use LETRA: http://ip:puerto`. Equivalente exacto al
    comando manual que antes había que escribir en una terminal aparte."""
    if platform.system() != "Windows":
        return False, ("Montar unidades de red con 'net use' solo funciona en Windows. "
                        "En este sistema no se puede ejecutar el comando.")

    comando = ["net", "use", letra, f"http://{ip}:{puerto}"]
    try:
        resultado = subprocess.run(
            comando, capture_output=True, text=True, timeout=20,
        )
    except subprocess.TimeoutExpired:
        return False, (f"⏱️ Tiempo de espera agotado conectando a {ip}:{puerto}. "
                        "Comprueba que el móvil está en la misma red WiFi y que el "
                        "servidor WebDAV sigue abierto en la app.")
    except OSError as e:
        return False, f"No se pudo ejecutar 'net use': {e}"

    salida = (resultado.stdout + resultado.stderr).strip()
    if resultado.returncode == 0:
        return True, salida or f"{letra} conectada correctamente a {ip}:{puerto}."
    return False, salida or f"'net use' devolvió el código de error {resultado.returncode}."


def desmontar(letra: str) -> tuple[bool, str]:
    """Ejecuta `net use LETRA: /delete /y`."""
    if platform.system() != "Windows":
        return False, "Desmontar unidades de red con 'net use' solo funciona en Windows."

    comando = ["net", "use", letra, "/delete", "/y"]
    try:
        resultado = subprocess.run(comando, capture_output=True, text=True, timeout=15)
    except OSError as e:
        return False, f"No se pudo ejecutar 'net use': {e}"

    salida = (resultado.stdout + resultado.stderr).strip()
    if resultado.returncode == 0:
        return True, salida or f"{letra} desconectada."
    return False, salida or f"'net use /delete' devolvió el código de error {resultado.returncode}."


def rutas_origen_por_defecto() -> list[Path]:
    """Subcarpetas típicas de capturas de pantalla de Android, una pareja
    por cada móvil conectado. Sustituye a la antigua lista fija basada en
    una única unidad Z: — ahora se genera dinámicamente según cuántas
    conexiones haya guardadas."""
    rutas: list[Path] = []
    for conexion in cargar_conexiones():
        letra = conexion["letra"]
        rutas.append(Path(rf"{letra}\Pictures\Screenshots"))
        rutas.append(Path(rf"{letra}\DCIM\Screenshots"))
    return rutas
