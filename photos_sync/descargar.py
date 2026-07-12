import json
import uuid
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.progress import track

from .carpetas import cargar_carpetas_guardadas
from .config import ARCHIVO_METADATOS_JSON, EXTENSIONES_VALIDAS, UNIDAD_WEBDAV

MetadatosCaptura = dict[str, Any]


def unidad_webdav_montada() -> bool:
    ruta = Path(UNIDAD_WEBDAV)
    return ruta.exists() or ruta.is_dir()


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


def obtener_fecha_real(nombre_archivo: str, mtime_fallback: float) -> str:
    """
    Intenta extraer la fecha exacta desde el nombre del archivo (Screenshot_20231024_153020).
    Es la forma más fiable porque WebDAV a menudo rompe las fechas del sistema de archivos.
    """
    # Busca Año, Mes, Día y Hora, Minuto, Segundo separados por cualquier cosa
    match_completo = re.search(r'(20\d{2})\D*(\d{2})\D*(\d{2})\D*(\d{2})\D*(\d{2})\D*(\d{2})', nombre_archivo)
    if match_completo:
        a, m, d, h, mn, s = match_completo.groups()
        # Validamos que los números tengan sentido como fechas
        if 1 <= int(m) <= 12 and 1 <= int(d) <= 31 and 0 <= int(h) <= 23:
            return f"{a}-{m}-{d} {h}:{mn}:{s}"
            
    # Si no tiene hora, buscamos solo la fecha (Año, Mes, Día)
    match_fecha = re.search(r'(20\d{2})\D*(\d{2})\D*(\d{2})', nombre_archivo)
    if match_fecha:
        a, m, d = match_fecha.groups()
        if 1 <= int(m) <= 12 and 1 <= int(d) <= 31:
            return f"{a}-{m}-{d} 12:00:00"
            
    # Fallback: Si el nombre no tiene fecha, confiamos en lo que diga el disco
    return datetime.fromtimestamp(mtime_fallback).strftime('%Y-%m-%d %H:%M:%S')


def exportar_metadatos_json() -> None:
    print("Searching for screenshots on Z: drive and extracting metadata...\n")

    if not unidad_webdav_montada():
        print(f"❌ Drive {UNIDAD_WEBDAV} is not mounted or accessible.")
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
                    errores_listado += 1
        except OSError as e:
            errores_listado += 1

    metadatos_previos = cargar_metadatos_existentes()
    metadatos_actuales = {}
    nuevos = 0
    sin_cambios = 0

    for archivo in track(archivos_encontrados, description="Analyzing screenshots..."):
        ruta_str = str(archivo)

        try:
            stats = archivo.stat()
            peso_mb = round(stats.st_size / (1024 * 1024), 2)
            anterior = metadatos_previos.get(ruta_str)

            if (anterior
                    and anterior.get("tamano_mb") == peso_mb
                    and anterior.get("mtime") == stats.st_mtime):
                if "id" not in anterior:
                    anterior["id"] = str(uuid.uuid4())
                metadatos_actuales[ruta_str] = anterior
                sin_cambios += 1
                continue

            # --- MAGIA AQUÍ: Sacamos la fecha real del nombre ---
            fecha_legible = obtener_fecha_real(archivo.name, stats.st_mtime)

            id_captura = anterior["id"] if anterior and "id" in anterior else str(uuid.uuid4())

            metadatos_actuales[ruta_str] = {
                "id": id_captura,
                "archivo": archivo.name,
                "formato": archivo.suffix.lower().replace('.', ''),
                "tamano_mb": peso_mb,
                "mtime": stats.st_mtime,
                "fecha_captura": fecha_legible,
                "ruta_original": ruta_str
            }
            nuevos += 1

        except OSError:
            continue

    eliminados = len(metadatos_previos) - sum(1 for r in metadatos_previos if r in metadatos_actuales)
    lista_metadatos = list(metadatos_actuales.values())

    if len(lista_metadatos) > 0:
        with open(ARCHIVO_METADATOS_JSON, 'w', encoding='utf-8') as f:
            json.dump(lista_metadatos, f, indent=4, ensure_ascii=False)
        print("-" * 50)
        print(f"✅ Success! Metadata extracted and dates corrected.")
    else:
        print("❌ No screenshots found to export.")

if __name__ == "__main__":
    exportar_metadatos_json()