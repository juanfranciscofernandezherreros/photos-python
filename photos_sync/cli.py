import argparse
import logging
import sys
from typing import Callable

from .config import ARCHIVO_LOG_ORQUESTADOR
from . import descargar, organizar, comprimir

# Cada paso es (nombre a mostrar, función a llamar). Ya no se lanzan
# scripts sueltos con subprocess: al ser un paquete instalado, el CLI
# importa y llama directamente a las funciones de cada módulo.
PasoPipeline = tuple[str, Callable[[], None]]

PASOS: list[PasoPipeline] = [
    ("Descargar metadatos (Z: -> JSON)", descargar.exportar_metadatos_json),
    ("Organizar por fecha (JSON -> agrupados/AAAA/MM/DD)", organizar.organizar_capturas_por_fecha),
    ("Comprimir por día (agrupados -> .zip)", comprimir.comprimir_carpetas_por_dia),
]


def configurar_logging() -> logging.Logger:
    """Registra cada ejecución en un archivo además de en consola. Así, si
    el orquestador corre desatendido (por ejemplo desde el Programador de
    tareas de Windows) y algo falla, queda un rastro que revisar.

    El archivo de log se crea en la carpeta desde la que se ejecuta el
    comando (el cwd), igual que metadatos_screenshots.json — piensa en esa
    carpeta como el "espacio de trabajo" del pipeline."""
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
    """Ejecuta la función de un paso y atrapa cualquier excepción, para que
    un fallo en un paso no tumbe el proceso completo sin dejar rastro."""
    log.info(f"⏳ ['INICIANDO'] -> {nombre}")

    try:
        funcion()
    except Exception as e:
        log.error(f"❌ ['ERROR'] -> Fallo al ejecutar '{nombre}': {e}")
        return False

    log.info(f"✅ ['COMPLETADO'] -> {nombre}")
    return True


def ejecutar_pasos(pasos_a_ejecutar: list[PasoPipeline]) -> bool:
    """Ejecuta los pasos en cadena, parando en el primer fallo. Devuelve
    True si todos terminaron bien. Compartida entre el modo interactivo y
    el modo CLI/desatendido."""
    log.info("=" * 55)
    log.info("⚙️ INICIANDO EJECUCIÓN")
    log.info("=" * 55)

    for nombre, funcion in pasos_a_ejecutar:
        if not ejecutar_paso(nombre, funcion):
            log.error("🛑 Se detuvo la orquestación en cadena debido a un error previo.")
            return False

    log.info("=" * 55)
    log.info("🎉 TODOS LOS PASOS SELECCIONADOS SE HAN EJECUTADO CORRECTAMENTE")
    log.info("=" * 55)
    return True


def parsear_argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="photos-sync",
        description="Pipeline de fotos: descarga, organiza y comprime capturas desde Z:. "
                     "Sin argumentos abre el menú interactivo."
    )
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument(
        "--todo", action="store_true",
        help="Ejecuta los 3 pasos en orden (equivalente a la opción T del menú)."
    )
    grupo.add_argument(
        "--pasos", type=str, metavar="1,2,3",
        help="Ejecuta solo los pasos indicados, separados por comas (ej: --pasos 1,3)."
    )
    return parser.parse_args()


def menu_interactivo() -> None:
    while True:
        print("\n" + "=" * 55)
        print("🚀 PHOTOS-SYNC - MENÚ PRINCIPAL")
        print("=" * 55)

        for i, (nombre, _fn) in enumerate(PASOS, 1):
            print(f"  [{i}] - {nombre}")

        print("-" * 55)
        print("  [T] - Ejecutar TODO en orden")
        print("  [S] - Salir")
        print("=" * 55)

        opcion = input("\nElige una opción (ej: 1, 1,3, T o S): ").strip().upper()

        if opcion == 'S':
            print("\n👋 Saliendo...")
            break

        pasos_a_ejecutar: list[PasoPipeline] = []

        if opcion == 'T':
            pasos_a_ejecutar = PASOS
        else:
            try:
                entradas = opcion.replace(' ', ',').split(',')
                indices = [int(x.strip()) for x in entradas if x.strip()]

                for indice in indices:
                    if 1 <= indice <= len(PASOS):
                        pasos_a_ejecutar.append(PASOS[indice - 1])
                    else:
                        print(f"\n⚠️ Ignorando opción '{indice}': Fuera de rango.")
            except ValueError:
                print("\n❌ Entrada no válida. Por favor, usa números, 'T' para todo o 'S' para salir.")
                continue

        if not pasos_a_ejecutar:
            continue

        ejecutar_pasos(pasos_a_ejecutar)


def modo_cli(args: argparse.Namespace) -> None:
    """Ejecución no interactiva: para lanzar desde una terminal con flags
    o programada en el Programador de tareas de Windows. Termina el proceso
    con código 0 (éxito) o 1 (fallo) para que el planificador lo detecte."""
    pasos_a_ejecutar: list[PasoPipeline]

    if args.todo:
        pasos_a_ejecutar = PASOS
    else:
        try:
            indices = [int(x.strip()) for x in args.pasos.split(',') if x.strip()]
        except ValueError:
            log.error("❌ --pasos debe ser una lista de números separados por comas, ej: --pasos 1,2,3")
            sys.exit(1)

        pasos_a_ejecutar = []
        for indice in indices:
            if 1 <= indice <= len(PASOS):
                pasos_a_ejecutar.append(PASOS[indice - 1])
            else:
                log.warning(f"⚠️ Ignorando opción '{indice}': fuera de rango.")

        if not pasos_a_ejecutar:
            log.error("❌ Ningún paso válido que ejecutar.")
            sys.exit(1)

    exito = ejecutar_pasos(pasos_a_ejecutar)
    sys.exit(0 if exito else 1)


def main() -> None:
    """Punto de entrada del comando `photos-sync` (ver pyproject.toml)."""
    argumentos = parsear_argumentos()

    if argumentos.todo or argumentos.pasos:
        modo_cli(argumentos)
    else:
        menu_interactivo()


if __name__ == "__main__":
    main()
