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
from pathlib import Path

from ..folders import load_saved_destination, load_destination_config
from ..config import ORGANIZED_DIR, VALID_EXTENSIONS
from .. import ssh_connection

from rich.progress import track


def _local_organized_folder() -> Path:
    """La misma carpeta local que usa organizar.py, sea la configurada
    explícitamente o la de por defecto."""
    destino_str = load_saved_destination()
    return Path(destino_str) if destino_str else ORGANIZED_DIR


def _destination_servers() -> list[ssh_connection.SSHConnection]:
    """Servidores SSH a los que hay que upload: los de rol 'destino'/'ambos',
    más el marcado explícitamente como destino principal en carpetas.py
    (por si el usuario eligió un servidor SSH como destino desde el
    selector de carpetas en vez de desde el panel de conexiones SSH)."""
    servidores = {c["alias"]: c for c in ssh_connection.connections_by_role("destino")}

    config_destino = load_destination_config()
    if config_destino.get("tipo") == "ssh":
        alias = config_destino.get("alias", "")
        c = ssh_connection.get_connection(alias)
        if c:
            servidores[alias] = c

    return list(servidores.values())


def upload_organized_to_ssh() -> None:
    print("Checking for SSH destination servers...\n")

    if not ssh_connection.paramiko_available():
        print("❌ Missing library 'paramiko'. Install it with: pip install paramiko")
        return

    servidores = _destination_servers()
    if not servidores:
        print("⏭️ No SSH server configured as destination — skipping this step. "
              "(Configure one in 'Conexión SSH' with role 'destino' or 'ambos' if you want a "
              "backup copy on a Linux server.)")
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

        subidas = 0
        ya_existian = 0
        errores = 0

        try:
            with ssh_connection.SSHClient(conexion_ssh) as cliente:
                for archivo_local in track(archivos_locales, description=f"Uploading to {conexion_ssh['alias']}..."):
                    ruta_relativa = archivo_local.relative_to(carpeta_local).as_posix()
                    ruta_remota = f"{ruta_remota_base}/{ruta_relativa}"

                    try:
                        tamano_remoto = cliente.remote_exists(ruta_remota)
                        if tamano_remoto is not None and tamano_remoto == archivo_local.stat().st_size:
                            ya_existian += 1
                            continue

                        cliente.upload(archivo_local, ruta_remota)
                        subidas += 1
                    except OSError as e:
                        print(f"⚠️ Could not upload '{ruta_relativa}': {e}")
                        errores += 1

        except Exception as e:
            print(f"❌ Could not connect to '{conexion_ssh['alias']}': {e}")
            continue

        print("-" * 50)
        print(f"UPLOAD SUMMARY for '{conexion_ssh['alias']}':")
        print(f"  - New files uploaded: {subidas}")
        print(f"  - Already existed on server: {ya_existian}")
        if errores > 0:
            print(f"  - Errors: {errores}")
        print()


if __name__ == "__main__":
    upload_organized_to_ssh()
