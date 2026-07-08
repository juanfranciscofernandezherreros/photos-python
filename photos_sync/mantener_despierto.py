"""
Evita que Windows entre en modo de suspensión mientras el pipeline está
corriendo. Sin esto, si el PC se queda inactivo el tiempo suficiente
(o el usuario lo bloquea con Win+L y el equipo decide suspenderse igualmente
según su plan de energía), la ejecución se pausa a mitad de camino junto con
la conexión de red hacia el teléfono.

El bloqueo de pantalla (Win+L) en sí NO pausa procesos en ejecución — solo
la suspensión real del equipo lo hace. Este módulo solo evita esa
suspensión; no mantiene la pantalla encendida ni evita que el propio
teléfono bloquee su pantalla (eso es un ajuste del lado del móvil).

En sistemas que no son Windows, las funciones no hacen nada (no-op), para
que el resto del código funcione igual en cualquier plataforma.
"""
import contextlib
import sys
from typing import Iterator

# Flags de la API de Windows (kernel32.SetThreadExecutionState)
_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001


@contextlib.contextmanager
def evitar_suspension() -> Iterator[None]:
    """Mientras dura este bloque `with`, le pide a Windows que no suspenda
    el equipo. Al salir del bloque (incluso si hay una excepción), se lo
    revierte automáticamente para no dejar el PC "despierto para siempre"
    por accidente."""
    if sys.platform != "win32":
        yield
        return

    import ctypes  # import local: solo hace falta en Windows

    try:
        ctypes.windll.kernel32.SetThreadExecutionState(  # type: ignore[attr-defined]
            _ES_CONTINUOUS | _ES_SYSTEM_REQUIRED
        )
        yield
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(_ES_CONTINUOUS)  # type: ignore[attr-defined]
