import json
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn

from .config import ARCHIVO_METADATOS_JSON, CARPETA_SCREENSHOTS_AGRUPADOS, NUM_HILOS_COPIA

MetadatosCaptura = dict[str, Any]
ResultadoCopia = tuple[str, str, str]


def procesar_captura(captura: MetadatosCaptura, destino_base: Path) -> ResultadoCopia:
    ruta_origen = Path(captura["ruta_original"])
    nombre: str = captura["archivo"]

    if not ruta_origen.exists():
        return ("no_encontrado", nombre, f"⚠️ No encontrado en Z: (¿Se borró?): {ruta_origen}")

    try:
        fecha = datetime.strptime(captura["fecha_captura"], '%Y-%m-%d %H:%M:%S')
        ano, mes, dia = fecha.strftime('%Y'), fecha.strftime('%m'), fecha.strftime('%d')

        carpeta_destino = destino_base / ano / mes / dia
        carpeta_destino.mkdir(parents=True, exist_ok=True)
        ruta_destino = carpeta_destino / nombre

        if ruta_destino.exists():
            return ("omitido", nombre, f"⏭️ Omitido (ya organizada): {nombre}")

        shutil.copy2(ruta_origen, ruta_destino)
        return ("copiado", nombre, f"📂 {nombre}  ->  {ano}/{mes}/{dia}/")

    except Exception as e:
        return ("error", nombre, f"❌ Error al copiar '{nombre}': {e}")


def organizar_capturas_por_fecha() -> None:
    destino_base = CARPETA_SCREENSHOTS_AGRUPADOS

    if not Path(ARCHIVO_METADATOS_JSON).exists():
        print(f"❌ Error: No se encontró el archivo '{ARCHIVO_METADATOS_JSON}' en esta carpeta.")
        return

    print(f"Leyendo '{ARCHIVO_METADATOS_JSON}'...\n")
    print(f"Organizando capturas en: {destino_base.resolve()} (usando {NUM_HILOS_COPIA} hilos)")
    print("-" * 50)

    try:
        with open(ARCHIVO_METADATOS_JSON, 'r', encoding='utf-8') as f:
            lista_capturas: list[MetadatosCaptura] = json.load(f)
    except json.JSONDecodeError:
        print(f"❌ Error: El archivo '{ARCHIVO_METADATOS_JSON}' está corrupto o no tiene un formato JSON válido.")
        return
    except Exception as e:
        print(f"❌ Ocurrió un error inesperado leyendo el JSON: {e}")
        return

    contadores: dict[str, int] = {"copiado": 0, "omitido": 0, "no_encontrado": 0, "error": 0}

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        TextColumn("restante:"),
        TimeRemainingColumn(),
    ) as progress:
        tarea = progress.add_task("Organizando capturas", total=len(lista_capturas))

        with ThreadPoolExecutor(max_workers=NUM_HILOS_COPIA) as pool:
            futuros = [pool.submit(procesar_captura, captura, destino_base) for captura in lista_capturas]

            for futuro in as_completed(futuros):
                estado, _nombre, mensaje = futuro.result()
                progress.console.print(mensaje)
                contadores[estado] += 1
                progress.advance(tarea)

    print("-" * 50)
    print("RESUMEN DE LA ORGANIZACIÓN:")
    print(f"  - Archivos copiados y agrupados: {contadores['copiado']}")
    print(f"  - Archivos omitidos (ya existían): {contadores['omitido']}")
    errores_totales = contadores['no_encontrado'] + contadores['error']
    if errores_totales > 0:
        print(f"  - Errores de lectura/escritura: {errores_totales}")

    if contadores['copiado'] > 0:
        print("\n✅ ¡Tus capturas se han copiado y ordenado correctamente!")


if __name__ == "__main__":
    organizar_capturas_por_fecha()
