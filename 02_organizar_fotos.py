import json
import shutil
from pathlib import Path

def copiar_capturas_desde_json():
    # ==========================================
    # CONFIGURACIÓN
    # ==========================================
    archivo_json = "metadatos_screenshots.json"
    carpeta_destino_pc = r"C:\Develop\screenshots"
    # ==========================================
    
    destino = Path(carpeta_destino_pc)
    
    # Creamos la carpeta C:\Develop\screenshots si no existe todavía
    destino.mkdir(parents=True, exist_ok=True)
    
    # Comprobamos que el archivo JSON esté donde debe estar
    if not Path(archivo_json).exists():
        print(f"❌ Error: No se encontró el archivo '{archivo_json}' en esta carpeta.")
        return

    print(f"Leyendo '{archivo_json}'...\n")
    print(f"Copiando archivos a: {destino.resolve()}")
    print("-" * 50)
    
    archivos_copiados = 0
    archivos_omitidos = 0
    errores = 0
    
    try:
        # Abrimos y cargamos el JSON
        with open(archivo_json, 'r', encoding='utf-8') as f:
            lista_capturas = json.load(f)
            
        # Recorremos cada diccionario dentro de la lista
        for captura in lista_capturas:
            ruta_origen = Path(captura["ruta_original"])
            ruta_destino = destino / captura["archivo"]
            
            # 1. Comprobamos si la imagen sigue existiendo en Z:
            if ruta_origen.exists():
                # 2. Comprobamos si ya la habíamos copiado antes para no duplicar trabajo
                if not ruta_destino.exists():
                    try:
                        # shutil.copy2 copia el archivo y mantiene la fecha de creación intacta
                        shutil.copy2(ruta_origen, ruta_destino)
                        print(f"✅ Copiado: {captura['archivo']}")
                        archivos_copiados += 1
                    except Exception as e:
                        print(f"❌ Error al copiar '{captura['archivo']}': {e}")
                        errores += 1
                else:
                    print(f"⏭️ Omitido (ya estaba en C:): {captura['archivo']}")
                    archivos_omitidos += 1
            else:
                print(f"⚠️ No encontrado en Z: (¿Se borró?): {ruta_origen}")
                errores += 1
                
        print("-" * 50)
        print("RESUMEN DE LA OPERACIÓN:")
        print(f"  - Archivos copiados con éxito: {archivos_copiados}")
        print(f"  - Archivos omitidos (ya existían): {archivos_omitidos}")
        print(f"  - Errores de lectura/escritura: {errores}")
        
    except json.JSONDecodeError:
        print(f"❌ Error: El archivo '{archivo_json}' está corrupto o no tiene un formato JSON válido.")
    except Exception as e:
        print(f"❌ Ocurrió un error inesperado: {e}")

if __name__ == "__main__":
    copiar_capturas_desde_json()