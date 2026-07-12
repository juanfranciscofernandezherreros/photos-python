import argparse
import logging
import sys
from typing import Callable

from .config import ARCHIVO_LOG_ORQUESTADOR
from .mantener_despierto import evitar_suspension
from . import descargar, organizar, comprimir, resumen

PasoPipeline = tuple[str, Callable[[], None]]

PASOS: list[PasoPipeline] = [
    ("Download metadata (Z: -> JSON)", descargar.exportar_metadatos_json),
    ("Organize by date (JSON -> grouped/YYYY/MM/DD)", organizar.organizar_capturas_por_fecha),
    ("Compress by day (grouped -> .zip)", comprimir.comprimir_carpetas_por_dia),
    ("Count photos by day (JSON -> resumen_por_dia.json)", resumen.generar_resumen_por_dia),
]


def configurar_logging() -> logging.Logger:
    logger = logging.getLogger("photos_sync")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formato = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    manejador_consola = logging.StreamHandler(sys.stdout)
    manejador_consola.setFormatter(formato)
    logger.addHandler(manejador_consola)

    manejador_archivo = logging.FileHandler(ARCHIVO_LOG_ORQUESTADOR, encoding="utf-8")
    manejador_archivo.setFormatter(formato)
    logger.addHandler(manejador_archivo)

    return logger


log: logging.Logger = configurar_logging()


def ejecutar_paso(nombre: str, funcion: Callable[[], None]) -> bool:
    log.info(f"⏳ ['STARTING'] -> {nombre}")

    try:
        funcion()
    except Exception as e:
        log.error(f"❌ ['ERROR'] -> Failed to execute '{nombre}': {e}")
        return False

    log.info(f"✅ ['COMPLETED'] -> {nombre}")
    return True


def ejecutar_pasos(pasos_a_ejecutar: list[PasoPipeline]) -> bool:
    with evitar_suspension():
        log.info("=" * 55)
        log.info("⚙️ STARTING EXECUTION")
        log.info("=" * 55)

        for nombre, funcion in pasos_a_ejecutar:
            if not ejecutar_paso(nombre, funcion):
                log.error("🛑 Orchestration stopped due to a previous error.")
                return False

        log.info("=" * 55)
        log.info("🎉 ALL SELECTED STEPS HAVE BEEN EXECUTED SUCCESSFULLY")
        log.info("=" * 55)
        return True


def parsear_argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="photos-sync",
        description="Photos pipeline: downloads, organizes, and compresses screenshots from Z:. "
                     "Without arguments, opens the graphical window."
    )
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument(
        "--todo", action="store_true",
        help="Executes all 3 steps in order (equivalent to menu option T)."
    )
    grupo.add_argument(
        "--pasos", type=str, metavar="1,2,3",
        help="Executes only the specified steps, separated by commas (e.g., --steps 1,3)."
    )
    return parser.parse_args()


def abrir_interfaz_grafica() -> None:
    """Lanza la ventana principal (PyQt6) con botones para cada paso y un
    panel de log integrado. Sustituye al antiguo menú de texto."""
    try:
        from .main_window import main as gui_main
    except ImportError:
        print("\n❌ Could not load PyQt6. Install it with: pip install PyQt6")
        return

    gui_main()


def modo_cli(args: argparse.Namespace) -> None:
    pasos_a_ejecutar: list[PasoPipeline]

    if args.todo:
        pasos_a_ejecutar = PASOS
    else:
        try:
            indices = [int(x.strip()) for x in args.pasos.split(',') if x.strip()]
        except ValueError:
            log.error("❌ --steps must be a comma-separated list of numbers, e.g., --steps 1,2,3")
            sys.exit(1)

        pasos_a_ejecutar = []
        for indice in indices:
            if 1 <= indice <= len(PASOS):
                pasos_a_ejecutar.append(PASOS[indice - 1])
            else:
                log.warning(f"⚠️ Ignoring option '{indice}': out of range.")

        if not pasos_a_ejecutar:
            log.error("❌ No valid steps to execute.")
            sys.exit(1)

    exito = ejecutar_pasos(pasos_a_ejecutar)
    sys.exit(0 if exito else 1)


def main() -> None:
    argumentos = parsear_argumentos()

    if argumentos.todo or argumentos.pasos:
        # Modo desatendido (Programador de tareas de Windows, sin pantalla):
        # se queda en consola/log a propósito, no abre ninguna ventana.
        modo_cli(argumentos)
    else:
        # Uso normal e interactivo: siempre la interfaz gráfica.
        abrir_interfaz_grafica()


if __name__ == "__main__":
    main()
