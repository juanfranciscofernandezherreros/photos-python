import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

from rich.progress import track

from .config import (
    ARCHIVO_METADATOS_JSON,
    CARPETA_SCREENSHOTS_AGRUPADOS,
    CARPETA_ZIPS,
    BORRAR_ORIGINALES_TRAS_COMPRIMIR,
)

MetadatosCaptura = dict[str, Any]


def zip_es_valido(ruta_zip: Path) -> bool:
    try:
        with zipfile.ZipFile(ruta_zip, 'r') as zf:
            return zf.testzip() is None
    except zipfile.BadZipFile:
        return False


def cargar_metadatos() -> list[MetadatosCaptura]:
    archivo = Path(ARCHIVO_METADATOS_JSON)
    if not archivo.exists():
        return []
    try:
        with open(archivo, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"⚠️ Could not read '{ARCHIVO_METADATOS_JSON}' to record ZIP paths: {e}")
        return []


def guardar_metadatos(lista_capturas: list[MetadatosCaptura]) -> None:
    if not lista_capturas:
        return
    try:
        with open(ARCHIVO_METADATOS_JSON, 'w', encoding='utf-8') as f:
            json.dump(lista_capturas, f, indent=4, ensure_ascii=False)
    except OSError as e:
        print(f"⚠️ Could not update '{ARCHIVO_METADATOS_JSON}' with ZIP paths: {e}")


def marcar_ruta_zip(lista_capturas: list[MetadatosCaptura], carpeta_dia: Path, ruta_zip: Path) -> None:
    """Anota en cada metadato la ruta del .zip donde acabó, para poder
    localizar el archivo aunque su carpeta original ya haya sido borrada."""
    for captura in lista_capturas:
        ruta_destino = captura.get("ruta_destino")
        if ruta_destino and Path(ruta_destino).parent == carpeta_dia:
            captura["ruta_zip"] = str(ruta_zip)


def comprimir_carpetas_por_dia() -> None:
    carpeta_base = CARPETA_SCREENSHOTS_AGRUPADOS
    carpeta_zips = CARPETA_ZIPS

    if not carpeta_base.exists():
        print(f"❌ Error: Folder '{carpeta_base}' does not exist.")
        return

    carpeta_zips.mkdir(parents=True, exist_ok=True)

    lista_capturas = cargar_metadatos()

    print(f"Searching for day folders in: {carpeta_base.resolve()}...\n")
    if BORRAR_ORIGINALES_TRAS_COMPRIMIR:
        print("⚠️ BORRAR_ORIGINALES_TRAS_COMPRIMIR is enabled: day folders will be\n"
              "   deleted once their .zip file is verified as valid.\n")
    print("-" * 50)

    zips_creados: int = 0
    errores: int = 0
    carpetas_borradas: int = 0

    carpetas_dia: list[Path] = [
        carpeta_dia
        for carpeta_ano in carpeta_base.iterdir()
        if carpeta_ano.is_dir() and carpeta_ano.name != "Comprimidos"
        for carpeta_mes in carpeta_ano.iterdir()
        if carpeta_mes.is_dir()
        for carpeta_dia in carpeta_mes.iterdir()
        if carpeta_dia.is_dir()
    ]

    for carpeta_dia in track(carpetas_dia, description="Compressing by day..."):
        ano = carpeta_dia.parent.parent.name
        mes = carpeta_dia.parent.name
        dia = carpeta_dia.name

        nombre_archivo = f"Capturas_{ano}-{mes}-{dia}"
        ruta_zip = carpeta_zips / f"{nombre_archivo}.zip"
        zip_recien_creado = False

        if ruta_zip.exists():
            print(f"⏭️ Skipped: '{nombre_archivo}.zip' already exists.")
        else:
            try:
                shutil.make_archive(
                    base_name=str(carpeta_zips / nombre_archivo),
                    format='zip',
                    root_dir=str(carpeta_dia)
                )

                print(f"📦 Compressed: {ano}\\{mes}\\{dia} -> {nombre_archivo}.zip")
                zips_creados += 1
                zip_recien_creado = True

            except Exception as e:
                print(f"❌ Error compressing day {ano}-{mes}-{dia}: {e}")
                errores += 1
                continue

        marcar_ruta_zip(lista_capturas, carpeta_dia, ruta_zip)

        if BORRAR_ORIGINALES_TRAS_COMPRIMIR:
            if zip_es_valido(ruta_zip):
                shutil.rmtree(carpeta_dia)
                carpetas_borradas += 1
                if not zip_recien_creado:
                    print(f"🗑️ Verified and deleted original for: {ano}\\{mes}\\{dia}")
            else:
                print(f"⚠️ '{nombre_archivo}.zip' failed integrity verification; "
                      f"original folder {carpeta_dia} NOT deleted")
                errores += 1

    guardar_metadatos(lista_capturas)

    print("-" * 50)
    print("COMPRESSION SUMMARY:")
    print(f"  - New ZIP files created: {zips_creados}")
    if BORRAR_ORIGINALES_TRAS_COMPRIMIR:
        print(f"  - Original folders deleted after verification: {carpetas_borradas}")
    if errores > 0:
        print(f"  - Errors found: {errores}")

    print(f"\n📁 Your compressed files are ready in: {carpeta_zips.resolve()}")


if __name__ == "__main__":
    comprimir_carpetas_por_dia()
