import shutil
import os
import json
from datetime import datetime
from pathlib import Path

from rich.progress import track

from .carpetas import cargar_destino_guardado
from .config import ARCHIVO_METADATOS_JSON, CARPETA_SCREENSHOTS_AGRUPADOS


def organizar_capturas_por_fecha() -> None:
    """Copia cada captura listada en ARCHIVO_METADATOS_JSON a
    destino/AAAA/MM/DD según su fecha real, repara la fecha del archivo
    copiado y guarda la ruta de destino ("ruta_destino") de vuelta en el
    JSON de metadatos para que comprimir.py y resumen.py puedan usarla."""
    print(f"Reading '{ARCHIVO_METADATOS_JSON}'...\n")

    archivo_metadatos = Path(ARCHIVO_METADATOS_JSON)
    if not archivo_metadatos.exists():
        print(f"❌ '{ARCHIVO_METADATOS_JSON}' not found. Run step 1 (download) first.")
        return

    try:
        with open(archivo_metadatos, 'r', encoding='utf-8') as f:
            lista = json.load(f)
    except json.JSONDecodeError:
        print(f"❌ '{ARCHIVO_METADATOS_JSON}' is corrupt. Run step 1 (download) again.")
        return

    if not lista:
        print("❌ No captures in the metadata file to organize.")
        return

    destino_str = cargar_destino_guardado()
    destino_base = Path(destino_str) if destino_str else CARPETA_SCREENSHOTS_AGRUPADOS
    print(f"Destination: {destino_base.resolve()}\n")

    copiadas = 0
    ya_existian = 0
    errores = 0

    for captura in track(lista, description="Organizing by date..."):
        try:
            fecha = datetime.strptime(captura["fecha_captura"], '%Y-%m-%d %H:%M:%S')
            carpeta_destino = destino_base / fecha.strftime('%Y/%m/%d')
            carpeta_destino.mkdir(parents=True, exist_ok=True)

            destino_final = carpeta_destino / captura["archivo"]

            if destino_final.exists():
                ya_existian += 1
            else:
                shutil.copy2(captura["ruta_original"], destino_final)
                # Repara la fecha en el sistema de archivos (WebDAV suele romperla)
                ts = fecha.timestamp()
                os.utime(destino_final, (ts, ts))
                copiadas += 1

            captura["ruta_destino"] = str(destino_final)

        except (KeyError, OSError, ValueError) as e:
            print(f"⚠️ Could not organize '{captura.get('archivo', '?')}': {e}")
            errores += 1

    with open(archivo_metadatos, 'w', encoding='utf-8') as f:
        json.dump(lista, f, indent=4, ensure_ascii=False)

    print("-" * 50)
    print("ORGANIZE SUMMARY:")
    print(f"  - New copies: {copiadas}")
    print(f"  - Already existed: {ya_existian}")
    if errores > 0:
        print(f"  - Errors: {errores}")
    print(f"\n📁 Organized files are in: {destino_base.resolve()}")


if __name__ == "__main__":
    organizar_capturas_por_fecha()
