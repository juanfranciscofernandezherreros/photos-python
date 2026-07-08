import json
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.progress import track

from .carpetas import cargar_carpetas_guardadas
from .config import ARCHIVO_METADATOS_JSON, EXTENSIONES_VALIDAS, UNIDAD_WEBDAV

MetadatosCaptura = dict[str, Any]


def unidad_webdav_montada() -> bool:
    """Comprueba si la unidad de red (Z:) está montada y accesible."""
    return Path(f"{UNIDAD_WEBDAV}\\").exists()


def cargar_metadatos_existentes() -> dict[str, MetadatosCaptura]:
    """Carga el JSON de una ejecución anterior, si existe. Devuelve un dict
    indexado por ruta_original para poder comparar rápido contra lo que hay
    ahora mismo en el teléfono."""
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

    # Comprobación temprana: si la unidad de red ni siquiera está montada,
    # avisamos claramente en vez de dejar que parezca "no hay capturas".
    if not unidad_webdav_montada():
        print(f"❌ La unidad {UNIDAD_WEBDAV} no está montada o no es accesible.")
        print(f"   Ejecuta 'net use {UNIDAD_WEBDAV} http://<ip_telefono>:8080' y vuelve a intentarlo.")
        return

    # Fase 1: listamos los archivos candidatos en cada carpeta. Enumerar el
    # árbol de directorios suele ser rápido incluso por red; lo lento viene
    # después, al pedir el stat() (tamaño y fecha) de cada uno por WebDAV.
    # cargar_carpetas_guardadas() usa la selección hecha con
    # `photos-sync-carpetas` si existe, o si no, las de config.py.
    archivos_encontrados: list[Path] = []
    for ruta in cargar_carpetas_guardadas():
        if ruta.exists() and ruta.is_dir():
            print(f"✅ Extrayendo datos de: {ruta}")
            archivos_encontrados.extend(
                a for a in ruta.rglob('*') if a.is_file() and a.suffix.lower() in EXTENSIONES_VALIDAS
            )
        else:
            print(f"⚠️ Subcarpeta no encontrada en la unidad: {ruta}")

    # Metadatos de la ejecución anterior, para hacer un merge incremental
    # en vez de sobrescribir el JSON entero cada vez.
    metadatos_previos: dict[str, MetadatosCaptura] = cargar_metadatos_existentes()
    metadatos_actuales: dict[str, MetadatosCaptura] = {}
    nuevos = 0
    sin_cambios = 0

    # Fase 2: por cada archivo, comparamos con lo que ya sabíamos y
    # recalculamos si hace falta. La barra de progreso ayuda porque esta
    # parte puede tardar en colecciones grandes sobre una unidad de red.
    for archivo in track(archivos_encontrados, description="Analizando capturas..."):
        ruta_str = str(archivo)

        # Si ya la teníamos registrada, con el mismo tamaño Y la
        # misma fecha de modificación, reutilizamos la entrada tal
        # cual (evita recalcular sin motivo). Comparar solo el
        # tamaño no basta: dos capturas distintas pueden pesar
        # exactamente lo mismo.
        stats = archivo.stat()
        peso_mb = round(stats.st_size / (1024 * 1024), 2)
        anterior = metadatos_previos.get(ruta_str)

        if (anterior
                and anterior.get("tamano_mb") == peso_mb
                and anterior.get("mtime") == stats.st_mtime):
            metadatos_actuales[ruta_str] = anterior
            sin_cambios += 1
            continue

        # Es nueva o ha cambiado: recalculamos sus metadatos
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

    # Cualquier ruta que estaba en el JSON anterior pero ya no aparece en el
    # teléfono se considera borrada y no se arrastra al nuevo JSON.
    eliminados = len(metadatos_previos) - sum(
        1 for ruta_str in metadatos_previos if ruta_str in metadatos_actuales
    )

    lista_metadatos = list(metadatos_actuales.values())
    contador_total = len(lista_metadatos)

    # Si encontramos al menos una captura, creamos el archivo JSON
    if contador_total > 0:
        # Escribimos los datos en el archivo
        # indent=4 hace que el JSON se vea ordenado y tabulado
        # ensure_ascii=False permite que los caracteres especiales se guarden bien
        with open(ARCHIVO_METADATOS_JSON, 'w', encoding='utf-8') as f:
            json.dump(lista_metadatos, f, indent=4, ensure_ascii=False)

        print("-" * 50)
        print(f"✅ ¡Éxito! El JSON tiene ahora {contador_total} capturas.")
        print(f"   - Nuevas o actualizadas: {nuevos}")
        print(f"   - Sin cambios: {sin_cambios}")
        if eliminados > 0:
            print(f"   - Eliminadas del teléfono (quitadas del JSON): {eliminados}")
        print(f"📁 Puedes abrir el archivo: {ARCHIVO_METADATOS_JSON}")
    else:
        print("❌ No se encontraron capturas para exportar.")


if __name__ == "__main__":
    exportar_metadatos_json()