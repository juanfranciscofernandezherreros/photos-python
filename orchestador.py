import argparse
import logging
import subprocess
import sys
from pathlib import Path

from config import ARCHIVO_LOG_ORQUESTADOR

# Carpeta donde vive este propio script. Todas las rutas se anclan aquí,
# así el orquestador funciona sin importar desde qué carpeta se ejecute.
CARPETA_SCRIPTS = Path(__file__).resolve().parent

PASOS = [
    CARPETA_SCRIPTS / "01_descargar_archivos.py",
    CARPETA_SCRIPTS / "02_organizar_por_fecha.py",
    CARPETA_SCRIPTS / "03_comprimir.py",
]


def configurar_logging():
    """Registra cada ejecución en un archivo además de en consola. Así, si
    el orquestador corre desatendido (por ejemplo desde el Programador de
    tareas de Windows) y algo falla, queda un rastro que revisar."""
    logger = logging.getLogger("orquestador")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formato = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    manejador_consola = logging.StreamHandler(sys.stdout)
    manejador_consola.setFormatter(formato)
    logger.addHandler(manejador_consola)

    manejador_archivo = logging.FileHandler(CARPETA_SCRIPTS / ARCHIVO_LOG_ORQUESTADOR, encoding="utf-8")
    manejador_archivo.setFormatter(formato)
    logger.addHandler(manejador_archivo)

    return logger


log = configurar_logging()


def ejecutar_script(ruta_script):
    """Ejecuta un script de Python y comprueba si hay errores."""
    log.info(f"⏳ ['INICIANDO'] -> {ruta_script.name}")

    # Ejecutamos el script (cwd fijado a la carpeta de scripts por si alguno
    # usa rutas relativas, como el JSON de metadatos)
    resultado = subprocess.run([sys.executable, str(ruta_script)], cwd=CARPETA_SCRIPTS)

    if resultado.returncode != 0:
        log.error(f"❌ ['ERROR'] -> Fallo al ejecutar {ruta_script.name} (código {resultado.returncode}).")
        return False

    log.info(f"✅ ['COMPLETADO'] -> {ruta_script.name}")
    return True


def ejecutar_pasos(rutas_a_ejecutar):
    """Comprueba que existan los scripts y los ejecuta en cadena, parando
    en el primer fallo. Devuelve True si todos terminaron bien.
    Compartida entre el modo interactivo y el modo CLI/desatendido."""
    archivos_faltantes = [p for p in rutas_a_ejecutar if not p.exists()]
    if archivos_faltantes:
        for p in archivos_faltantes:
            log.warning(f"⚠️ ['ADVERTENCIA'] -> No se encuentra el archivo: {p}")
        log.error("❌ Faltan scripts. Corrige las rutas o nombres antes de continuar.")
        return False

    log.info("=" * 55)
    log.info("⚙️ INICIANDO EJECUCIÓN")
    log.info("=" * 55)

    for paso in rutas_a_ejecutar:
        if not ejecutar_script(paso):
            log.error("🛑 Se detuvo la orquestación en cadena debido a un error previo.")
            return False

    log.info("=" * 55)
    log.info("🎉 TODOS LOS PASOS SELECCIONADOS SE HAN EJECUTADO CORRECTAMENTE")
    log.info("=" * 55)
    return True


def parsear_argumentos():
    parser = argparse.ArgumentParser(
        description="Orquestador del pipeline de fotos. Sin argumentos abre el menú interactivo."
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


def menu_interactivo():
    while True:
        print("\n" + "=" * 55)
        print("🚀 ORQUESTADOR DE PROCESOS - MENÚ PRINCIPAL")
        print("=" * 55)

        for i, paso in enumerate(PASOS, 1):
            print(f"  [{i}] - {paso.name}")

        print("-" * 55)
        print("  [T] - Ejecutar TODO en orden")
        print("  [S] - Salir del orquestador")
        print("=" * 55)

        opcion = input("\nElige una opción (ej: 1, 1,3, T o S): ").strip().upper()

        if opcion == 'S':
            print("\n👋 Saliendo del orquestador...")
            break

        rutas_a_ejecutar = []

        if opcion == 'T':
            rutas_a_ejecutar = PASOS
        else:
            try:
                entradas = opcion.replace(' ', ',').split(',')
                indices = [int(x.strip()) for x in entradas if x.strip()]

                for indice in indices:
                    if 1 <= indice <= len(PASOS):
                        rutas_a_ejecutar.append(PASOS[indice - 1])
                    else:
                        print(f"\n⚠️ Ignorando opción '{indice}': Fuera de rango.")
            except ValueError:
                print("\n❌ Entrada no válida. Por favor, usa números, 'T' para todo o 'S' para salir.")
                continue

        if not rutas_a_ejecutar:
            continue

        ejecutar_pasos(rutas_a_ejecutar)


def modo_cli(args):
    """Ejecución no interactiva: para lanzar desde una terminal con flags
    o programada en el Programador de tareas de Windows. Termina el proceso
    con código 0 (éxito) o 1 (fallo) para que el planificador lo detecte."""
    if args.todo:
        rutas_a_ejecutar = PASOS
    else:
        try:
            indices = [int(x.strip()) for x in args.pasos.split(',') if x.strip()]
        except ValueError:
            log.error("❌ --pasos debe ser una lista de números separados por comas, ej: --pasos 1,2,3")
            sys.exit(1)

        rutas_a_ejecutar = []
        for indice in indices:
            if 1 <= indice <= len(PASOS):
                rutas_a_ejecutar.append(PASOS[indice - 1])
            else:
                log.warning(f"⚠️ Ignorando opción '{indice}': fuera de rango.")

        if not rutas_a_ejecutar:
            log.error("❌ Ningún paso válido que ejecutar.")
            sys.exit(1)

    exito = ejecutar_pasos(rutas_a_ejecutar)
    sys.exit(0 if exito else 1)


if __name__ == "__main__":
    argumentos = parsear_argumentos()

    if argumentos.todo or argumentos.pasos:
        modo_cli(argumentos)
    else:
        menu_interactivo()
