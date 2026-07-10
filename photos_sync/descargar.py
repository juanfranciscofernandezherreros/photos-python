import json
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.progress import track

from .carpetas import cargar_carpetas_guardadas
from .config import ARCHIVO_METADATOS_JSON, EXTENSIONES_VALIDAS, UNIDAD_WEBDAV

MetadatosCaptura = dict[str, Any]


def unidad_webdav_montada() -> bool:
    return Path(f"{UNIDAD_WEBDAV}\\").exists()


def cargar_metadatos_existentes() -> dict[str, MetadatosCaptura]:
    archivo = Path(ARCHIVO_METADATOS_JSON)
    if not archivo.exists():
        return {}

    try:
        with open(archivo, 'r', encoding='utf-8') as f:
            lista_previa: list[MetadatosCaptura] = json.load(f)
        return {item["ruta_original"]: item for item in lista_previa}
    except (json.JSONDecodeError, KeyError):
        print(f"⚠️ Existing '{ARCHIVO_METADATOS_JSON}' is corrupt, it will be regenerated from scratch.\n")
        return {}


def exportar_metadatos_json() -> None:
    print("Searching for screenshots on Z: drive and extracting metadata...\n")

    if not unidad_webdav_montada():
        print(f"❌ Drive {UNIDAD_WEBDAV} is not mounted or accessible.")
        print(f"   Execute 'net use {UNIDAD_WEBDAV} http://<phone_ip>:8080' and try again.")
        return

    archivos_encontrados: list[Path] = []
    errores_listado = 0

    for ruta in cargar_carpetas_guardadas():
        if not (ruta.exists() and ruta.is_dir()):
            print(f"⚠️ Subfolder not found on drive: {ruta}")
            continue

        print(f"✅ Extracting data from: {ruta}")
        try:
            for candidato in ruta.rglob('*'):
                try:
                    if candidato.is_file() and candidato.suffix.lower() in EXTENSIONES_VALIDAS:
                        archivos_encontrados.append(candidato)
                except OSError as e:
                    print(f"   ⚠️ Could not check '{candidato.name}': {e}")
                    errores_listado += 1
        except OSError as e:
            print(f"   ❌ Error listing '{ruta}': {e}")
            errores_listado += 1

    metadatos_previos: dict[str, MetadatosCaptura] = cargar_metadatos_existentes()
    metadatos_actuales: dict[str, MetadatosCaptura] = {}
    nuevos = 0
    sin_cambios = 0
    errores_analisis = 0

    for archivo in track(archivos_encontrados, description="Analyzing screenshots..."):
        ruta_str = str(archivo)

        try:
            stats = archivo.stat()
            peso_mb = round(stats.st_size / (1024 * 1024), 2)
            anterior = metadatos_previos.get(ruta_str)

            if (anterior
                    and anterior.get("tamano_mb") == peso_mb
                    and anterior.get("mtime") == stats.st_mtime):
                metadatos_actuales[ruta_str] = anterior
                sin_cambios += 1
                continue

            fecha_legible = datetime.fromtimestamp(stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S')

            metadatos_actuales[ruta_str] = {
                "archivo": archivo.name,
                "formato": archivo.suffix.lower().replace('.', ''),
                "tamano_mb": peso_mb,
                "mtime": stats.st_mtime,
                "fecha_captura": fecha_legible,
                "ruta_original": ruta_str
            }
            nuevos += 1

        except OSError as e:
            print(f"   ⚠️ Could not read '{archivo.name}', skipping: {e}")
            errores_analisis += 1
            continue

    eliminados = len(metadatos_previos) - sum(
        1 for ruta_str in metadatos_previos if ruta_str in metadatos_actuales
    )

    lista_metadatos = list(metadatos_actuales.values())
    contador_total = len(lista_metadatos)

    if contador_total > 0:
        with open(ARCHIVO_METADATOS_JSON, 'w', encoding='utf-8') as f:
            json.dump(lista_metadatos, f, indent=4, ensure_ascii=False)

        print("-" * 50)
        print(f"✅ Success! The JSON now contains {contador_total} screenshots.")
        print(f"   - New or updated: {nuevos}")
        print(f"   - Unchanged: {sin_cambios}")
        if eliminados > 0:
            print(f"   - Deleted from phone (removed from JSON): {eliminados}")
        total_errores = errores_listado + errores_analisis
        if total_errores > 0:
            print(f"   - ⚠️ Files skipped due to read error: {total_errores} (check warnings above)")
        print(f"📁 You can open the file: {ARCHIVO_METADATOS_JSON}")
    else:
        print("❌ No screenshots found to export.")
        if errores_listado + errores_analisis > 0:
            print(f"   ({errores_listado + errores_analisis} files failed to read — check warnings above)")


if __name__ == "__main__":
    exportar_metadatos_json()
