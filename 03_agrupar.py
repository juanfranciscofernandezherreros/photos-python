import shutil
from datetime import datetime

from config import CARPETA_SCREENSHOTS, CARPETA_SCREENSHOTS_AGRUPADOS, EXTENSIONES_VALIDAS


def organizar_fotos_por_fecha():
    carpeta_origen = CARPETA_SCREENSHOTS
    carpeta_destino_base = CARPETA_SCREENSHOTS_AGRUPADOS

    if not carpeta_origen.exists():
        print(f"❌ Error: La carpeta de origen '{carpeta_origen}' no existe.")
        return

    print(f"Leyendo capturas desde: {carpeta_origen.resolve()}")
    print(f"Copiando agrupadas en: {carpeta_destino_base.resolve()}\n")
    print("-" * 50)

    archivos_copiados = 0
    errores = 0

    # Buscamos solo los archivos sueltos en la raíz de la carpeta de origen
    for archivo in carpeta_origen.glob('*'):

        # Filtramos para asegurarnos de que solo copiamos imágenes
        if archivo.is_file() and archivo.suffix.lower() in EXTENSIONES_VALIDAS:
            try:
                # Extraemos la fecha de modificación del archivo (que conservamos del móvil)
                timestamp = archivo.stat().st_mtime
                fecha = datetime.fromtimestamp(timestamp)

                # Extraemos año, mes y día (en formato de dos dígitos, ej: 06, 29)
                ano = fecha.strftime('%Y')
                mes = fecha.strftime('%m')
                dia = fecha.strftime('%d')

                # Construimos la ruta de las subcarpetas en el nuevo destino
                carpeta_destino = carpeta_destino_base / ano / mes / dia

                # Creamos las carpetas si no existen (parents=True crea toda la ruta de golpe)
                carpeta_destino.mkdir(parents=True, exist_ok=True)

                # Ruta final donde quedará el archivo
                ruta_final = carpeta_destino / archivo.name

                # Copiamos el archivo preservando metadatos
                if not ruta_final.exists():
                    shutil.copy2(archivo, ruta_final)
                    print(f"📂 {archivo.name}  ->  {ano}/{mes}/{dia}/")
                    archivos_copiados += 1
                else:
                    print(f"⚠️ Omitido: '{archivo.name}' ya existía en la carpeta de destino.")

            except Exception as e:
                print(f"❌ Error al copiar '{archivo.name}': {e}")
                errores += 1

    print("-" * 50)
    print("RESUMEN DE LA ORGANIZACIÓN:")
    print(f"  - Archivos copiados y agrupados: {archivos_copiados}")
    if errores > 0:
        print(f"  - Errores encontrados: {errores}")

    if archivos_copiados > 0:
        print("\n✅ ¡Tus capturas se han copiado y ordenado correctamente!")


if __name__ == "__main__":
    organizar_fotos_por_fecha()
