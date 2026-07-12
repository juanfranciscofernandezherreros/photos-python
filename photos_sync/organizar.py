import json
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn

from .carpetas import cargar_destino_guardado
from .config import ARCHIVO_METADATOS_JSON, CARPETA_SCREENSHOTS_AGRUPADOS, NUM_HILOS_COPIA

MetadatosCaptura = dict[str, Any]
ResultadoCopia = tuple[str, str, str]


def procesar_captura(captura: MetadatosCaptura, destino_base: Path) -> ResultadoCopia:
    ruta_origen = Path(captura["ruta_original"])
    nombre: str = captura["archivo"]

    if not ruta_origen.exists():
        return ("not_found", nombre, f"⚠️ Not found on Z: (Was it deleted?): {ruta_origen}")

    try:
        fecha = datetime.strptime(captura["fecha_captura"], '%Y-%m-%d %H:%M:%S')
        ano, mes, dia = fecha.strftime('%Y'), fecha.strftime('%m'), fecha.strftime('%d')

        carpeta_destino = destino_base / ano / mes / dia
        carpeta_destino.mkdir(parents=True, exist_ok=True)
        ruta_destino = carpeta_destino / nombre

        if ruta_destino.exists():
            captura["ruta_destino"] = str(ruta_destino)
            return ("skipped", nombre, f"⏭️ Skipped (already organized): {nombre}")

        shutil.copy2(ruta_origen, ruta_destino)
        captura["ruta_destino"] = str(ruta_destino)
        return ("copied", nombre, f"📂 {nombre}  ->  {ano}/{mes}/{dia}/")

    except Exception as e:
        return ("error", nombre, f"❌ Error copying '{nombre}': {e}")


def organizar_capturas_por_fecha() -> None:
    # AQUÍ ESTÁ EL CAMBIO PRINCIPAL: Leemos el JSON en lugar de la variable estática
    destino_str = cargar_destino_guardado()
    destino_base = Path(destino_str) if destino_str else CARPETA_SCREENSHOTS_AGRUPADOS

    if not Path(ARCHIVO_METADATOS_JSON).exists():
        print(f"❌ Error: File '{ARCHIVO_METADATOS_JSON}' not found in this folder.")
        return

    print(f"Reading '{ARCHIVO_METADATOS_JSON}'...\n")
    print(f"Organizing screenshots in: {destino_base.resolve()} (using {NUM_HILOS_COPIA} threads)")
    print("-" * 50)

    try:
        with open(ARCHIVO_METADATOS_JSON, 'r', encoding='utf-8') as f:
            lista_capturas: list[MetadatosCaptura] = json.load(f)
    except json.JSONDecodeError:
        print(f"❌ Error: File '{ARCHIVO_METADATOS_JSON}' is corrupt or not a valid JSON format.")
        return
    except Exception as e:
        print(f"❌ An unexpected error occurred while reading the JSON: {e}")
        return

    contadores: dict[str, int] = {"copied": 0, "skipped": 0, "not_found": 0, "error": 0}

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        TextColumn("restante:"),
        TimeRemainingColumn(),
    ) as progress:
        tarea = progress.add_task("Organizing screenshots", total=len(lista_capturas))

        with ThreadPoolExecutor(max_workers=NUM_HILOS_COPIA) as pool:
            futuros = [pool.submit(procesar_captura, captura, destino_base) for captura in lista_capturas]

            for futuro in as_completed(futuros):
                estado, _nombre, mensaje = futuro.result()
                progress.console.print(mensaje)
                contadores[estado] += 1
                progress.advance(tarea)

    try:
        with open(ARCHIVO_METADATOS_JSON, 'w', encoding='utf-8') as f:
            json.dump(lista_capturas, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ Could not update '{ARCHIVO_METADATOS_JSON}' with destination paths: {e}")

    print("-" * 50)
    print("ORGANIZATION SUMMARY:")
    print(f"  - Files copied and grouped: {contadores['copied']}")
    print(f"  - Files skipped (already existed): {contadores['skipped']}")
    errores_totales = contadores['not_found'] + contadores['error']
    if errores_totales > 0:
        print(f"  - Read/write errors: {errores_totales}")

    if contadores['copied'] > 0:
        print("\n✅ Your screenshots have been copied and organized successfully!")


if __name__ == "__main__":
    organizar_capturas_por_fecha()