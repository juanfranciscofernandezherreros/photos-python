import shutil, os, json
from datetime import datetime
from pathlib import Path
from .carpetas import cargar_destino_guardado
from .config import ARCHIVO_METADATOS_JSON, CARPETA_SCREENSHOTS_AGRUPADOS

def organizar():
    destino_str = cargar_destino_guardado()
    destino_base = Path(destino_str) if destino_str else CARPETA_SCREENSHOTS_AGRUPADOS
    
    with open(ARCHIVO_METADATOS_JSON, 'r', encoding='utf-8') as f:
        lista = json.load(f)
    
    for captura in lista:
        fecha = datetime.strptime(captura["fecha_captura"], '%Y-%m-%d %H:%M:%S')
        carpeta_destino = destino_base / fecha.strftime('%Y/%m/%d')
        carpeta_destino.mkdir(parents=True, exist_ok=True)
        
        destino_final = carpeta_destino / captura["archivo"]
        if not destino_final.exists():
            shutil.copy2(captura["ruta_original"], destino_final)
        
        # Repara la fecha en el sistema de archivos de Windows
        ts = fecha.timestamp()
        os.utime(destino_final, (ts, ts))