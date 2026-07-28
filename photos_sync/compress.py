import shutil
import zipfile
from pathlib import Path
from typing import Any

from rich.progress import track

from .folders import load_saved_destination
from .config import (
    METADATA_JSON,
    ORGANIZED_DIR,
    ZIPS_DIR,
    DELETE_ORIGINALS_AFTER_COMPRESS,
)
from .json_io import read_json, write_json

MetadatosCaptura = dict[str, Any]


def zip_is_valid(ruta_zip: Path) -> bool:
    try:
        with zipfile.ZipFile(ruta_zip, 'r') as zf:
            return zf.testzip() is None
    except zipfile.BadZipFile:
        return False


def load_metadata() -> list[MetadatosCaptura]:
    datos = read_json(METADATA_JSON, default=[])
    return datos if isinstance(datos, list) else []


def save_metadata(lista_capturas: list[MetadatosCaptura]) -> None:
    if not lista_capturas:
        return
    try:
        write_json(METADATA_JSON, lista_capturas)
    except OSError as e:
        print(f"⚠️ Could not update '{METADATA_JSON}' with ZIP paths: {e}")


def mark_zip_path(lista_capturas: list[MetadatosCaptura], carpeta_dia: Path, ruta_zip: Path) -> None:
    for captura in lista_capturas:
        ruta_destino = captura.get("ruta_destino")
        if ruta_destino and Path(ruta_destino).parent == carpeta_dia:
            captura["ruta_zip"] = str(ruta_zip)


def compress_folders_by_day() -> None:
    # AQUÍ ESTÁ EL CAMBIO: Cargamos el destino dinámico para los zips
    destino_str = load_saved_destination()
    if destino_str:
        carpeta_base = Path(destino_str)
        carpeta_zips = carpeta_base / "Comprimidos"
    else:
        carpeta_base = ORGANIZED_DIR
        carpeta_zips = ZIPS_DIR

    if not carpeta_base.exists():
        print(f"❌ Error: Folder '{carpeta_base}' does not exist.")
        return

    carpeta_zips.mkdir(parents=True, exist_ok=True)

    lista_capturas = load_metadata()

    print(f"Searching for day folders in: {carpeta_base.resolve()}...\n")
    if DELETE_ORIGINALS_AFTER_COMPRESS:
        print("⚠️ DELETE_ORIGINALS_AFTER_COMPRESS is enabled: day folders will be\n"
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

        mark_zip_path(lista_capturas, carpeta_dia, ruta_zip)

        if DELETE_ORIGINALS_AFTER_COMPRESS:
            if zip_is_valid(ruta_zip):
                shutil.rmtree(carpeta_dia)
                carpetas_borradas += 1
                if not zip_recien_creado:
                    print(f"🗑️ Verified and deleted original for: {ano}\\{mes}\\{dia}")
            else:
                print(f"⚠️ '{nombre_archivo}.zip' failed integrity verification; "
                      f"original folder {carpeta_dia} NOT deleted")
                errores += 1

    save_metadata(lista_capturas)

    print("-" * 50)
    print("COMPRESSION SUMMARY:")
    print(f"  - New ZIP files created: {zips_creados}")
    if DELETE_ORIGINALS_AFTER_COMPRESS:
        print(f"  - Original folders deleted after verification: {carpetas_borradas}")
    if errores > 0:
        print(f"  - Errors found: {errores}")

    print(f"\n📁 Your compressed files are ready in: {carpeta_zips.resolve()}")


if __name__ == "__main__":
    compress_folders_by_day()