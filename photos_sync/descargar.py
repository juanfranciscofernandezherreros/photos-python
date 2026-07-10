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
        print(f"⚠️ '{ARCHIVO_METADATOS_JSON}' existente está corrupto, se regenerará desde cero.\n")
        return {}


def exportar_metadatos_json() -> None:
    print("Buscando capturas en la unidad Z: y extrayendo metadatos...\n")

    if not unidad_webdav_montada():
        print(f"❌ La unidad {UNIDAD_WEBDAV} no está montada o no es accesible.")
        print(f"   Ejecuta 'net use {UNIDAD_WEBDAV} http://<ip_telefono>:8080' y vuelve a intentarlo.")
        return

    archivos_encontrados: list[Path] = []
    errores_listado = 0

    for ruta in cargar_carpetas_guardadas():
        if not (ruta.exists() and ruta.is_dir()):
            print(f"⚠️ Subcarpeta no encontrada en la unidad: {ruta}")
            continue

        print(f"✅ Extrayendo datos de: {ruta}")
        try:
            for candidato in ruta.rglob('*'):
                try:
                    if candidato.is_file() and candidato.suffix.lower() in EXTENSIONES_VALIDAS:
                        archivos_encontrados.append(candidato)
                except OSError as e:
                    print(f"   ⚠️ No se pudo comprobar '{candidato.name}': {e}")
                    errores_listado += 1
        except OSError as e:
            print(f"   ❌ Error listando '{ruta}': {e}")
            errores_listado += 1

    metadatos_previos: dict[str, MetadatosCaptura] = cargar_metadatos_existentes()
    metadatos_actuales: dict[str, MetadatosCaptura] = {}
    nuevos = 0
    sin_cambios = 0
    errores_analisis = 0

    for archivo in track(archivos_encontrados, description="Analizando capturas..."):
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
            print(f"   ⚠️ No se pudo leer '{archivo.name}', se omite: {e}")
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
        print(f"✅ ¡Éxito! El JSON tiene ahora {contador_total} capturas.")
        print(f"   - Nuevas o actualizadas: {nuevos}")
        print(f"   - Sin cambios: {sin_cambios}")
        if eliminados > 0:
            print(f"   - Eliminadas del teléfono (quitadas del JSON): {eliminados}")
        total_errores = errores_listado + errores_analisis
        if total_errores > 0:
            print(f"   - ⚠️ Archivos omitidos por error de lectura: {total_errores} (revisa los avisos de arriba)")
        print(f"📁 Puedes abrir el archivo: {ARCHIVO_METADATOS_JSON}")
    else:
        print("❌ No se encontraron capturas para exportar.")
        if errores_listado + errores_analisis > 0:
            print(f"   ({errores_listado + errores_analisis} archivos fallaron al leerse — revisa los avisos de arriba)")


if __name__ == "__main__":
    exportar_metadatos_json()
