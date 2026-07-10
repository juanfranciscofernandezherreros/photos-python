import shutil
import zipfile
from pathlib import Path

from rich.progress import track

from .config import CARPETA_SCREENSHOTS_AGRUPADOS, CARPETA_ZIPS, BORRAR_ORIGINALES_TRAS_COMPRIMIR


def zip_es_valido(ruta_zip: Path) -> bool:
    try:
        with zipfile.ZipFile(ruta_zip, 'r') as zf:
            return zf.testzip() is None
    except zipfile.BadZipFile:
        return False


def comprimir_carpetas_por_dia() -> None:
    carpeta_base = CARPETA_SCREENSHOTS_AGRUPADOS
    carpeta_zips = CARPETA_ZIPS

    if not carpeta_base.exists():
        print(f"❌ Error: La carpeta '{carpeta_base}' no existe.")
        return

    carpeta_zips.mkdir(parents=True, exist_ok=True)

    print(f"Buscando carpetas de días en: {carpeta_base.resolve()}...\n")
    if BORRAR_ORIGINALES_TRAS_COMPRIMIR:
        print("⚠️ BORRAR_ORIGINALES_TRAS_COMPRIMIR está activado: las carpetas de\n"
              "   día se eliminarán en cuanto se compruebe que su .zip es válido.\n")
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

    for carpeta_dia in track(carpetas_dia, description="Comprimiendo por día..."):
        ano = carpeta_dia.parent.parent.name
        mes = carpeta_dia.parent.name
        dia = carpeta_dia.name

        nombre_archivo = f"Capturas_{ano}-{mes}-{dia}"
        ruta_zip = carpeta_zips / f"{nombre_archivo}.zip"
        zip_recien_creado = False

        if ruta_zip.exists():
            print(f"⏭️ Omitido: '{nombre_archivo}.zip' ya existe.")
        else:
            try:
                shutil.make_archive(
                    base_name=str(carpeta_zips / nombre_archivo),
                    format='zip',
                    root_dir=str(carpeta_dia)
                )

                print(f"📦 Comprimido: {ano}\\{mes}\\{dia} -> {nombre_archivo}.zip")
                zips_creados += 1
                zip_recien_creado = True

            except Exception as e:
                print(f"❌ Error al comprimir el día {ano}-{mes}-{dia}: {e}")
                errores += 1
                continue

        if BORRAR_ORIGINALES_TRAS_COMPRIMIR:
            if zip_es_valido(ruta_zip):
                shutil.rmtree(carpeta_dia)
                carpetas_borradas += 1
                if not zip_recien_creado:
                    print(f"🗑️ Verificado y borrado el original de: {ano}\\{mes}\\{dia}")
            else:
                print(f"⚠️ '{nombre_archivo}.zip' no pasó la verificación de integridad; "
                      f"NO se borra la carpeta original {carpeta_dia}")
                errores += 1

    print("-" * 50)
    print("RESUMEN DE COMPRESIÓN:")
    print(f"  - Nuevos archivos ZIP creados: {zips_creados}")
    if BORRAR_ORIGINALES_TRAS_COMPRIMIR:
        print(f"  - Carpetas originales borradas tras verificar: {carpetas_borradas}")
    if errores > 0:
        print(f"  - Errores encontrados: {errores}")

    print(f"\n📁 Tus archivos comprimidos están listos en: {carpeta_zips.resolve()}")


if __name__ == "__main__":
    comprimir_carpetas_por_dia()
