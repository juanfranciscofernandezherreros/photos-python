import json
from datetime import datetime
from pathlib import Path

from config import RUTAS_SCREENSHOTS_ORIGEN, ARCHIVO_METADATOS_JSON, EXTENSIONES_VALIDAS, UNIDAD_WEBDAV


def unidad_webdav_montada():
    """Comprueba si la unidad de red (Z:) está montada y accesible."""
    return Path(f"{UNIDAD_WEBDAV}\\").exists()


def exportar_metadatos_json():
    print("Buscando capturas en la unidad Z: y extrayendo metadatos...\n")

    # Comprobación temprana: si la unidad de red ni siquiera está montada,
    # avisamos claramente en vez de dejar que parezca "no hay capturas".
    if not unidad_webdav_montada():
        print(f"❌ La unidad {UNIDAD_WEBDAV} no está montada o no es accesible.")
        print(f"   Ejecuta 'net use {UNIDAD_WEBDAV} http://<ip_telefono>:8080' y vuelve a intentarlo.")
        return

    lista_metadatos = []
    contador_total = 0

    for ruta in RUTAS_SCREENSHOTS_ORIGEN:
        if ruta.exists() and ruta.is_dir():
            print(f"✅ Extrayendo datos de: {ruta}")

            # Recorremos todas las subcarpetas con rglob
            for archivo in ruta.rglob('*'):
                if archivo.is_file() and archivo.suffix.lower() in EXTENSIONES_VALIDAS:
                    # Obtenemos las estadísticas internas del archivo
                    stats = archivo.stat()

                    # Convertimos el tamaño a Megabytes (con 2 decimales)
                    peso_mb = round(stats.st_size / (1024 * 1024), 2)

                    # Obtenemos la fecha de modificación/creación y la hacemos legible
                    # st_mtime suele ser la fecha en la que se tomó la captura
                    fecha_timestamp = stats.st_mtime
                    fecha_legible = datetime.fromtimestamp(fecha_timestamp).strftime('%Y-%m-%d %H:%M:%S')

                    # Creamos un diccionario con toda la información de esta imagen
                    datos_imagen = {
                        "archivo": archivo.name,
                        "formato": archivo.suffix.lower().replace('.', ''),
                        "tamano_mb": peso_mb,
                        "fecha_captura": fecha_legible,
                        "ruta_original": str(archivo)
                    }

                    # Añadimos el diccionario a nuestra lista maestra
                    lista_metadatos.append(datos_imagen)
                    contador_total += 1
        else:
            print(f"⚠️ Subcarpeta no encontrada en la unidad: {ruta}")

    # Si encontramos al menos una captura, creamos el archivo JSON
    if contador_total > 0:
        # Escribimos los datos en el archivo
        # indent=4 hace que el JSON se vea ordenado y tabulado
        # ensure_ascii=False permite que los caracteres especiales se guarden bien
        with open(ARCHIVO_METADATOS_JSON, 'w', encoding='utf-8') as f:
            json.dump(lista_metadatos, f, indent=4, ensure_ascii=False)

        print("-" * 50)
        print(f"✅ ¡Éxito! Se ha creado el JSON con {contador_total} capturas.")
        print(f"📁 Puedes abrir el archivo: {ARCHIVO_METADATOS_JSON}")
    else:
        print("❌ No se encontraron capturas para exportar.")


if __name__ == "__main__":
    exportar_metadatos_json()
