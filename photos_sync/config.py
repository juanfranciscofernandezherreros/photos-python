from pathlib import Path

CARPETA_BASE_PC: Path = Path(r"C:\Develop")
CARPETA_SCREENSHOTS_AGRUPADOS: Path = CARPETA_BASE_PC / "screenshots_agrupados"
CARPETA_ZIPS: Path = CARPETA_SCREENSHOTS_AGRUPADOS / "Comprimidos"
ARCHIVO_METADATOS_JSON: str = "metadatos_screenshots.json"
ARCHIVO_CARPETAS_SELECCIONADAS: str = "carpetas_screenshots.json"
ARCHIVO_DESTINO_JSON = "destino_guardado.json"
ARCHIVO_RESUMEN_DIAS: str = "resumen_por_dia.json"
ARCHIVO_LOG_ORQUESTADOR: str = "orquestador.log"
ARCHIVO_CONEXIONES_JSON: str = "conexiones_webdav.json"
EXTENSIONES_VALIDAS: list[str] = ['.png', '.jpg', '.jpeg', '.webp']
NUM_HILOS_COPIA: int = 8
BORRAR_ORIGINALES_TRAS_COMPRIMIR: bool = False