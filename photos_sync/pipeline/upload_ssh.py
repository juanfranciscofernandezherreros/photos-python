"""
Paso opcional del pipeline: sube la carpeta ya organizada (destino local,
la misma que usa organizar.py) a un servidor Linux por SSH, si hay alguno
configurado con rol "destino" o "ambos" (ver ssh_conexion.py).

No sustituye a organizar.py: la organización por fecha sigue haciéndose
siempre en local primero (más rápido y permite reintentar si la subida
falla a mitad). Este paso simplemente refleja esa misma carpeta local en
el servidor remoto, manteniendo la estructura AAAA/MM/DD, y no vuelve a
upload un fichero si ya existe en remoto con el mismo tamaño.
"""
from __future__ import annotations

from pathlib import Path

from rich.progress import track

from .. import ssh_connection
from ..config import ORGANIZED_DIR, VALID_EXTENSIONS
from ..storage.folders import load_destination_config, load_saved_destination


def _local_organized_folder() -> Path:
    destino_str = load_saved_destination()
    return Path(destino_str) if destino_str else ORGANIZED_DIR


def _destination_servers() -> list[ssh_connection.SSHConnection]:
    servidores = {c["alias"]: c for c in ssh_connection.connections_by_role("destino")}
    config_destino = load_destination_config()
    if config_destino.get("tipo") == "ssh":
        alias = config_destino.get("alias", "")
        c = ssh_connection.get_connection(alias)
        if c:
            servidores[alias] = c
    return list(servidores.values())


def _upload_with_retry(
    conexion_ssh: ssh_connection.SSHConnection,
    archivos_locales: list[Path],
    carpeta_local: Path,
) -> tuple[int, int, int]:
    """Upload files to one SSH server, retrying the whole connection up to 3 times
    on session-level failures. Returns (uploaded, already_existed, errors)."""
    ruta_remota_base = ssh_connection.effective_destination_path(conexion_ssh)
    subidas = 0
    ya_existian = 0
    errores: list[str] = []
    max_session_retries = 3

    for session_attempt in range(1, max_session_retries + 1):
        session_errors = 0
        try:
            with ssh_connection.SSHClient(conexion_ssh) as cliente:
                for archivo_local in track(
                    archivos_locales,
                    description=f"Uploading to {conexion_ssh['alias']}…"
                ):
                    ruta_relativa = archivo_local.relative_to(carpeta_local).as_posix()
                    ruta_remota = f"{ruta_remota_base}/{ruta_relativa}"
                    try:
                        remote_size = cliente.remote_exists(ruta_remota)
                        if remote_size is not None and remote_size == archivo_local.stat().st_size:
                            ya_existian += 1
                            continue
                        # SSHClient.upload already has per-file retry via @retry
                        cliente.upload(archivo_local, ruta_remota)
                        subidas += 1
                    except Exception:
                        errores.append(ruta_relativa)
                        session_errors += 1
            # Session completed without a connection-level crash — done
            break
        except Exception as e:
            if session_attempt < max_session_retries:
                import time
                wait = 5 * session_attempt
                print(f"\n  ⚠️  SSH session dropped (attempt {session_attempt}/{max_session_retries}): {e}."
                      f" Reconnecting in {wait}s…")
                time.sleep(wait)
            else:
                print(f"\n  ❌ Could not connect to '{conexion_ssh['alias']}' after "
                      f"{max_session_retries} attempts: {e}")
                raise

    return subidas, ya_existian, len(errores)


def upload_organized_to_ssh() -> None:
    print("Checking for SSH destination servers...\n")

    if not ssh_connection.paramiko_available():
        print("❌ Missing library 'paramiko'. Install it with: pip install paramiko")
        return

    servidores = _destination_servers()
    if not servidores:
        print("⏭️ No SSH server configured as destination — skipping this step.")
        return

    carpeta_local = _local_organized_folder()
    if not carpeta_local.exists():
        print(f"❌ Local folder '{carpeta_local}' does not exist yet. Run step 2 (organize) first.")
        return

    archivos_locales = [
        p for p in carpeta_local.rglob('*')
        if p.is_file() and p.suffix.lower() in VALID_EXTENSIONS
    ]
    if not archivos_locales:
        print(f"❌ No photos found in '{carpeta_local}' to upload.")
        return

    for conexion_ssh in servidores:
        ruta_remota_base = ssh_connection.effective_destination_path(conexion_ssh)
        print(f"📡 Uploading to '{conexion_ssh['alias']}' "
              f"({conexion_ssh['usuario']}@{conexion_ssh['host']}:{ruta_remota_base})...")

        try:
            subidas, ya_existian, errores = _upload_with_retry(
                conexion_ssh, archivos_locales, carpeta_local
            )
        except Exception as e:
            print(f"❌ Upload to '{conexion_ssh['alias']}' failed: {e}")
            continue

        print("-" * 50)
        print(f"UPLOAD SUMMARY for '{conexion_ssh['alias']}':")
        print(f"  - New files uploaded: {subidas}")
        print(f"  - Already existed on server: {ya_existian}")
        if errores:
            print(f"  - Errors: {errores}")
        print()


if __name__ == "__main__":
    upload_organized_to_ssh()
