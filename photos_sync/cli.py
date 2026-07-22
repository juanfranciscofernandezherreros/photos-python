import argparse
import logging
import sys
from typing import Callable

from .config import ARCHIVO_LOG_ORQUESTADOR
from .mantener_despierto import evitar_suspension
from . import descargar, organizar, comprimir, resumen, subir_ssh, ssh_conexion

PasoPipeline = tuple[str, Callable[[], None]]

PASOS: list[PasoPipeline] = [
    ("Download metadata (connected drives/SSH servers -> JSON)", descargar.exportar_metadatos_json),
    ("Organize by date (JSON -> grouped/YYYY/MM/DD)", organizar.organizar_capturas_por_fecha),
    ("Compress by day (grouped -> .zip)", comprimir.comprimir_carpetas_por_dia),
    ("Count photos by day (JSON -> resumen_por_dia.json)", resumen.generar_resumen_por_dia),
    ("Upload organized folder to SSH server (optional)", subir_ssh.subir_organizado_a_ssh),
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
        description="Photos pipeline: downloads, organizes, and compresses screenshots from your "
                     "connected phones (see 'Conexión WebDAV'). Without arguments, opens the graphical window."
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

    grupo_ssh = parser.add_argument_group(
        "SSH connections (Linux server)",
        "Manage saved SSH/SFTP connections without opening the graphical window. "
        "Useful for headless servers.",
    )
    grupo_ssh.add_argument(
        "--ssh-list", action="store_true",
        help="Lists the saved SSH connections."
    )
    grupo_ssh.add_argument(
        "--ssh-add", nargs=5, metavar=("ALIAS", "HOST", "PUERTO", "USUARIO", "RUTA_REMOTA"),
        help="Adds or updates an SSH connection to a Linux server."
    )
    grupo_ssh.add_argument(
        "--ssh-key", type=str, default="", metavar="RUTA_CLAVE",
        help="Private key path to use with --ssh-add (e.g. ~/.ssh/id_rsa). If omitted, "
             "the SSH agent / default keys will be tried when the connection is used."
    )
    grupo_ssh.add_argument(
        "--ssh-rol", type=str, default="origen", choices=ssh_conexion.ROLES_VALIDOS,
        help="Role for --ssh-add: 'origen' (scanned for photos), 'destino' (receives the "
             "organized folder), or 'ambos'. Default: origen."
    )
    grupo_ssh.add_argument(
        "--ssh-remove", type=str, metavar="ALIAS",
        help="Removes a saved SSH connection by its alias."
    )
    grupo_ssh.add_argument(
        "--ssh-test", type=str, metavar="ALIAS",
        help="Tests connectivity of a saved SSH connection by its alias."
    )

    return parser.parse_args()


def modo_gestion_ssh(args: argparse.Namespace) -> bool:
    """Procesa los argumentos --ssh-*. Devuelve True si se ha manejado
    alguno (y por tanto el programa debe terminar aquí, sin lanzar ni el
    pipeline ni la GUI)."""
    if args.ssh_list:
        conexiones = ssh_conexion.cargar_conexiones_ssh()
        if not conexiones:
            print("No hay conexiones SSH guardadas.")
        else:
            for c in conexiones:
                print(f"  {c['alias']}  ({c['usuario']}@{c['host']}:{c['puerto']})  "
                      f"ruta='{c['ruta_remota']}'  rol={c['rol']}"
                      f"{'  clave=' + c['clave_privada'] if c['clave_privada'] else ''}")
        return True

    if args.ssh_add:
        alias, host, puerto, usuario, ruta_remota = args.ssh_add
        try:
            puerto_int = int(puerto)
        except ValueError:
            log.error("❌ El puerto debe ser un número, ej: 22")
            sys.exit(1)
        ssh_conexion.anadir_o_actualizar_conexion_ssh(
            alias=alias, host=host, puerto=puerto_int, usuario=usuario,
            ruta_remota=ruta_remota, clave_privada=args.ssh_key, rol=args.ssh_rol,
        )
        print(f"✅ Conexión SSH '{alias}' guardada (rol: {args.ssh_rol}).")
        return True

    if args.ssh_remove:
        ssh_conexion.quitar_conexion_ssh(args.ssh_remove)
        print(f"✅ Conexión SSH '{args.ssh_remove}' eliminada (si existía).")
        return True

    if args.ssh_test:
        conexion_guardada = ssh_conexion.obtener_conexion(args.ssh_test)
        if conexion_guardada is None:
            print(f"❌ No existe ninguna conexión SSH guardada con el alias '{args.ssh_test}'.")
        elif not ssh_conexion.paramiko_disponible():
            print("❌ Falta la librería 'paramiko'. Instálala con: pip install paramiko")
        else:
            exito, mensaje = ssh_conexion.ClienteSSH(conexion_guardada).probar()
            print(mensaje)
        return True

    return False


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

    if modo_gestion_ssh(argumentos):
        return

    if argumentos.todo or argumentos.pasos:
        # Modo desatendido (Programador de tareas de Windows, sin pantalla):
        # se queda en consola/log a propósito, no abre ninguna ventana.
        modo_cli(argumentos)
    else:
        # Uso normal e interactivo: siempre la interfaz gráfica.
        abrir_interfaz_grafica()


if __name__ == "__main__":
    main()
