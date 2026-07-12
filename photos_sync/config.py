from pathlib import Path

UNIDAD_WEBDAV: str = "Z:"

RUTAS_SCREENSHOTS_ORIGEN: list[Path] = [
    Path(rf"{UNIDAD_WEBDAV}\Pictures\Screenshots"),
    Path(rf"{UNIDAD_WEBDAV}\DCIM\Screenshots"),
]

# Carpeta destino en el PC. Cámbiala aquí si quieres guardar los screenshots en otro sitio.
CARPETA_BASE_PC: Path = Path(r"C:\Develop")
# Dentro de esta carpeta se organizan los screenshots por año/mes/día de captura.
CARPETA_SCREENSHOTS_AGRUPADOS: Path = CARPETA_BASE_PC / "screenshots_agrupados"
CARPETA_ZIPS: Path = CARPETA_SCREENSHOTS_AGRUPADOS / "Comprimidos"
ARCHIVO_METADATOS_JSON: str = "metadatos_screenshots.json"
ARCHIVO_RESUMEN_DIAS: str = "resumen_por_dia.json"
ARCHIVO_LOG_ORQUESTADOR: str = "orquestador.log"
ARCHIVO_CARPETAS_SELECCIONADAS: str = "carpetas_screenshots.json"
EXTENSIONES_VALIDAS: list[str] = ['.png', '.jpg', '.jpeg', '.webp']
NUM_HILOS_COPIA: int = 8
BORRAR_ORIGINALES_TRAS_COMPRIMIR: bool = False
ARCHIVO_DESTINO_JSON = "destino_guardado.json"