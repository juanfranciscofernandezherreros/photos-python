from __future__ import annotations

import argparse
import logging
import sys
from typing import Callable

from . import ssh_connection
from .config import ORCHESTRATOR_LOG
from .keep_awake import prevent_sleep
from .pipeline import (
    classify_captures,
    compress_folders_by_day,
    generate_daily_summary,
    organize_captures_by_date,
    sync_captures,
    upload_organized_to_ssh,
)

PasoPipeline = tuple[str, Callable[[], None]]

PASOS: list[PasoPipeline] = [
    ("Sync & save captures", sync_captures),
    ("Organize by date", organize_captures_by_date),
    ("Classify photos", classify_captures),
    ("Compress by day", compress_folders_by_day),
    ("Generate summary", generate_daily_summary),
    ("Upload to SSH", upload_organized_to_ssh),
]


def configurar_logging() -> logging.Logger:
    logger = logging.getLogger("photos_sync")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    formato = logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")

    manejador_consola = logging.StreamHandler(sys.stdout)
    manejador_consola.setFormatter(formato)
    logger.addHandler(manejador_consola)

    manejador_archivo = logging.FileHandler(ORCHESTRATOR_LOG, encoding="utf-8")
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
    with prevent_sleep():
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
                     "connected phones. Without arguments, starts the web server at http://localhost:8765."
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
        "--ssh-rol", type=str, default="origen", choices=ssh_connection.VALID_ROLES,
        help="Role for --ssh-add: 'origen' (scanned for photos), 'destino' (receives the "
             "organized folder), or 'ambos'. Default: origen."
    )
    grupo_ssh.add_argument(
        "--ssh-remote-dest", type=str, default="", metavar="RUTA_REMOTA_DESTINO",
        help="Only relevant with --ssh-rol ambos: remote folder to upload the organized "
             "photos to. It MUST be different from RUTA_REMOTA (the origin folder being "
             "scanned), or the pipeline would re-scan its own uploads on every run. If "
             "omitted for role 'destino', RUTA_REMOTA is reused as the upload target."
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
        connections = ssh_connection.load_ssh_connections()
        if not connections:
            print("No SSH connections saved.")
        else:
            for c in connections:
                rd = c.get("ruta_remota_destino")
                extra_destino = f"  dest='{rd}'" if rd else ""
                print(f"  {c['alias']}  ({c['usuario']}@{c['host']}:{c['puerto']})  "
                      f"source='{c['ruta_remota']}'{extra_destino}  role={c['rol']}"
                      f"{'  key=' + c['clave_privada'] if c['clave_privada'] else ''}")
        return True

    if args.ssh_add:
        alias, host, puerto, usuario, ruta_remota = args.ssh_add
        try:
            puerto_int = int(puerto)
        except ValueError:
            log.error("❌ Port must be a number, e.g.: 22")
            sys.exit(1)
        try:
            ssh_connection.add_or_update_ssh_connection(
                alias=alias, host=host, puerto=puerto_int, usuario=usuario,
                ruta_remota=ruta_remota, clave_privada=args.ssh_key, rol=args.ssh_rol,
                ruta_remota_destino=args.ssh_remote_dest,
            )
        except ValueError as e:
            log.error(f"❌ {e}")
            sys.exit(1)
        print(f"✅ SSH connection '{alias}' saved (role: {args.ssh_rol}).")
        return True

    if args.ssh_remove:
        ssh_connection.remove_ssh_connection(args.ssh_remove)
        print(f"✅ SSH connection '{args.ssh_remove}' removed (if it existed).")
        return True

    if args.ssh_test:
        connection_guardada = ssh_connection.get_connection(args.ssh_test)
        if connection_guardada is None:
            print(f"❌ No SSH connection found with alias '{args.ssh_test}'.")
        elif not ssh_connection.paramiko_available():
            print("❌ Missing library 'paramiko'. Install it with: pip install paramiko")
        else:
            exito, mensaje = ssh_connection.SSHClient(connection_guardada).test_connection()
            print(mensaje)
        return True

    return False


def modo_cli(args: argparse.Namespace) -> None:
    # Verify DB is reachable before running the pipeline
    try:
        from .db import get_engine, init_db
        engine = get_engine()
        init_db(engine)
    except Exception as e:
        log.error(
            "❌ Cannot connect to the database: %s\n"
            "   Make sure DATABASE_URL is set and PostgreSQL is running.\n"
            "   Example: DATABASE_URL=postgresql://user:pass@localhost/photos_sync",
            e,
        )
        sys.exit(1)

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
        # Unattended mode (Windows Task Scheduler, headless): stays in the
        # console/log on purpose, runs the pipeline directly.
        modo_cli(argumentos)
    else:
        # No arguments: start the web server (the only UI now).
        print("Starting the Photos Sync web server…")
        print("Open http://localhost:8765 in your browser.\n")
        from .__main__ import main as web_main
        web_main()


if __name__ == "__main__":
    main()
