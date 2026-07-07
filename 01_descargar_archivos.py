import json
from pathlib import Path
from datetime import datetime

def exportar_metadatos_json():
    print("Buscando capturas en la unidad Z: y extrayendo metadatos...\n")
    
    # Las rutas de tu unidad de red WebDAV
    rutas_probables = [
        Path(r"Z:\Pictures\Screenshots"),
        Path(r"Z:\DCIM\Screenshots")
    ]
    
    lista_metadatos = []
    contador_total = 0
    
    for ruta in rutas_probables:
        if ruta.exists() and ruta.is_dir():
            print(f"✅ Extrayendo datos de: {ruta}")
            
            # Recorremos todas las subcarpetas con rglob
            for archivo in ruta.rglob('*'):
                if archivo.is_file() and archivo.suffix.lower() in ['.png', '.jpg', '.jpeg', '.webp']:
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

    # Si encontramos al menos una captura, creamos el archivo JSON
    if contador_total > 0:
        # Nombre del archivo JSON que se creará en tu carpeta de Python
        archivo_salida = "metadatos_screenshots.json"
        
        # Escribimos los datos en el archivo
        # indent=4 hace que el JSON se vea ordenado y tabulado
        # ensure_ascii=False permite que los caracteres especiales se guarden bien
        with open(archivo_salida, 'w', encoding='utf-8') as f:
            json.dump(lista_metadatos, f, indent=4, ensure_ascii=False)
            
        print("-" * 50)
        print(f"✅ ¡Éxito! Se ha creado el JSON con {contador_total} capturas.")
        print(f"📁 Puedes abrir el archivo: {archivo_salida}")
    else:
        print("❌ No se encontraron capturas para exportar.")

if __name__ == "__main__":
    exportar_metadatos_json()