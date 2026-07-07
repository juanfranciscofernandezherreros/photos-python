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

# 02_organizar_por_fecha.py copia aquí directamente desde Z:, organizando por AAAA/MM/DD
CARPETA_SCREENSHOTS_AGRUPADOS = CARPETA_BASE_PC / "screenshots_agrupados"

# 03_comprimir.py deja aquí los .zip generados
CARPETA_ZIPS = CARPETA_SCREENSHOTS_AGRUPADOS / "Comprimidos"

# ==========================================
# ARCHIVOS
# ==========================================
ARCHIVO_METADATOS_JSON = "metadatos_screenshots.json"

# Log de orchestador.py: útil para revisar qué pasó tras una ejecución
# desatendida (por ejemplo, lanzada por el Programador de tareas de Windows).
ARCHIVO_LOG_ORQUESTADOR = "orquestador.log"

# ==========================================
# FORMATOS DE IMAGEN VÁLIDOS
# ==========================================
# Usado por 01_descargar_archivos.py para filtrar qué archivos son capturas de pantalla.
EXTENSIONES_VALIDAS = ['.png', '.jpg', '.jpeg', '.webp']

# ==========================================
# RENDIMIENTO
# ==========================================
# Nº de copias simultáneas en 02_organizar_por_fecha.py. Como el cuello de
# botella es la latencia de la red WebDAV (no la CPU), varios hilos en
# paralelo aprovechan el tiempo de espera de unos para copiar con otros.
NUM_HILOS_COPIA = 8

# ==========================================
# LIMPIEZA DE ESPACIO
# ==========================================
# Si es True, 03_comprimir.py borra la carpeta de un día justo después de
# comprobar que su .zip se generó bien y se puede leer. Así no acabas con
# los originales sin comprimir Y el .zip ocupando espacio a la vez.
# Por defecto está en False: activa esto solo cuando confíes en el proceso,
# porque el borrado es irreversible.
BORRAR_ORIGINALES_TRAS_COMPRIMIR = False
