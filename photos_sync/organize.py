import shutil
import os
from datetime import datetime
from pathlib import Path

from rich.progress import track

from .folders import load_saved_destination
from .config import METADATA_JSON, ORGANIZED_DIR
from .json_io import read_json, write_json
from . import ssh_connection


def organize_captures_by_date() -> None:
    """Copia cada captura listada en METADATA_JSON a
    destino/AAAA/MM/DD según su fecha real, repara la fecha del archivo
    copiado y guarda la ruta de destino ("ruta_destino") de vuelta en el
    JSON de metadatos para que comprimir.py y resumen.py puedan usarla."""
    print(f"Reading '{METADATA_JSON}'...\n")

    lista = read_json(METADATA_JSON)
    if lista is None:
        print(f"❌ '{METADATA_JSON}' not found. Run step 1 (download) first.")
        return

    if not isinstance(lista, list):
        print(f"❌ '{METADATA_JSON}' is corrupt. Run step 1 (download) again.")
        return

    if not lista:
        print("❌ No captures in the metadata file to organize.")
        return

    destino_str = load_saved_destination()
    destino_base = Path(destino_str) if destino_str else ORGANIZED_DIR
    print(f"Destination: {destino_base.resolve()}\n")

    copiadas = 0
    ya_existian = 0
    errores = 0

    # Connectiones SSH abiertas de forma perezosa (una por alias, reutilizada
    # para todas las capturas de ese mismo servidor) y cerradas todas al
    # final, dentro/fuera de que todo vaya bien.
    clientes_ssh: dict[str, ssh_connection.SSHClient] = {}

    def _cliente_para(alias: str) -> ssh_connection.SSHClient:
        if alias not in clientes_ssh:
            conexion_guardada = ssh_connection.get_connection(alias)
            if conexion_guardada is None:
                raise RuntimeError(f"SSH connection '{alias}' is no longer saved")
            cliente = ssh_connection.SSHClient(conexion_guardada)
            cliente.connect()
            clientes_ssh[alias] = cliente
        return clientes_ssh[alias]

    try:
        for captura in track(lista, description="Organizing by date..."):
            try:
                fecha = datetime.strptime(captura["fecha_captura"], '%Y-%m-%d %H:%M:%S')
                carpeta_destino = destino_base / fecha.strftime('%Y/%m/%d')
                carpeta_destino.mkdir(parents=True, exist_ok=True)

                destino_final = carpeta_destino / captura["archivo"]

                if destino_final.exists():
                    ya_existian += 1
                else:
                    alias_ssh = captura.get("ssh_alias")
                    if alias_ssh:
                        # El origen es un servidor Linux: se trae por SFTP en vez de shutil.copy2.
                        _cliente_para(alias_ssh).download(captura["ssh_ruta_remota"], destino_final)
                    else:
                        shutil.copy2(captura["ruta_original"], destino_final)
                    # Repara la fecha en el sistema de archivos (WebDAV/SFTP suelen romperla)
                    ts = fecha.timestamp()
                    os.utime(destino_final, (ts, ts))
                    copiadas += 1

                captura["ruta_destino"] = str(destino_final)

            except (KeyError, OSError, ValueError, RuntimeError) as e:
                print(f"⚠️ Could not organize '{captura.get('archivo', '?')}': {e}")
                errores += 1
    finally:
        for cliente in clientes_ssh.values():
            cliente.close()

    write_json(METADATA_JSON, lista)

    print("-" * 50)
    print("ORGANIZE SUMMARY:")
    print(f"  - New copies: {copiadas}")
    print(f"  - Already existed: {ya_existian}")
    if errores > 0:
        print(f"  - Errors: {errores}")
    print(f"\n📁 Organized files are in: {destino_base.resolve()}")


if __name__ == "__main__":
    organize_captures_by_date()
