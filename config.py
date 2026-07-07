"""
Configuración centralizada del proyecto photos-python.

Todas las rutas y constantes que antes estaban repetidas o hardcodeadas
dentro de cada script viven ahora aquí. Si cambias de teléfono, de PC,
o de estructura de carpetas, solo tienes que tocar este archivo.
"""

from pathlib import Path

# ==========================================
# UNIDAD DE RED WEBDAV (el teléfono montado como Z:)
# ==========================================
# Letra de la unidad de red creada con: net use Z: http://<ip_telefono>:8080
UNIDAD_WEBDAV = "Z:"

# Carpetas donde el teléfono suele guardar las capturas de pantalla.
# Se comprueban en orden; puedes añadir más rutas si tu dispositivo usa otras.
RUTAS_SCREENSHOTS_ORIGEN = [
    Path(rf"{UNIDAD_WEBDAV}\Pictures\Screenshots"),
    Path(rf"{UNIDAD_WEBDAV}\DCIM\Screenshots"),
]

# ==========================================
# CARPETAS EN EL PC (Windows)
# ==========================================
CARPETA_BASE_PC = Path(r"C:\Develop")

# 02_organizar_fotos.py copia aquí los archivos tal cual, sin subcarpetas
CARPETA_SCREENSHOTS = CARPETA_BASE_PC / "screenshots"

# 03_agrupar.py copia aquí organizando por AAAA/MM/DD
CARPETA_SCREENSHOTS_AGRUPADOS = CARPETA_BASE_PC / "screenshots_agrupados"

# 04_comprimir.py deja aquí los .zip generados
CARPETA_ZIPS = CARPETA_SCREENSHOTS_AGRUPADOS / "Comprimidos"

# ==========================================
# ARCHIVOS
# ==========================================
ARCHIVO_METADATOS_JSON = "metadatos_screenshots.json"

# ==========================================
# FORMATOS DE IMAGEN VÁLIDOS
# ==========================================
# Usado por 01, 02 y 03 para filtrar qué archivos son capturas de pantalla.
EXTENSIONES_VALIDAS = ['.png', '.jpg', '.jpeg', '.webp']
