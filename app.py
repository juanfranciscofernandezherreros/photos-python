import sys
from PyQt6.QtWidgets import QApplication
from photos_sync.selector_carpetas import SelectorCarpetas
from photos_sync.descargar import exportar_metadatos_json
from photos_sync.organizar import organizar
from photos_sync.comprimir import comprimir_carpetas_por_dia

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    # 1. Abrir GUI
    window = SelectorCarpetas()
    window.show()
    
    # 2. Controlamos el cierre: si la ventana se cierra, se lanza el proceso
    if app.exec(): 
        pass 

    print("\n--- Configuración guardada. Iniciando proceso automático... ---")
    exportar_metadatos_json()
    organizar()
    comprimir_carpetas_por_dia()
    print("\n--- ¡Proceso finalizado con éxito! ---")

if __name__ == "__main__":
    main()