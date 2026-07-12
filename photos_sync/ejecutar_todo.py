# ejecutar_todo.py
import sys
from PyQt6.QtWidgets import QApplication
from photos_sync.selector_carpetas import SelectorCarpetas
from photos_sync.descargar import exportar_metadatos_json
from photos_sync.organizar import organizar
from photos_sync.comprimir import comprimir_carpetas_por_dia

def main():
    # 1. Abrir la GUI
    app = QApplication(sys.argv)
    window = SelectorCarpetas()
    window.show()
    app.exec() # El script se pausa aquí hasta que cierres la ventana

    # 2. Cuando la ventana se cierra, el proceso continúa:
    print("\n--- Configuración guardada. Iniciando proceso ---")
    exportar_metadatos_json() # Descarga los metadatos
    organizar()               # Mueve y repara fechas
    comprimir_carpetas_por_dia() # Comprime
    print("\n--- Proceso finalizado ---")

if __name__ == "__main__":
    main()