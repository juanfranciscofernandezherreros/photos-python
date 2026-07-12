# gui.py (El nuevo orquestador)
from PyQt6.QtCore import QThread, pyqtSignal
from photos_sync.descargar import exportar_metadatos_json
from photos_sync.organizar import organizar_capturas_por_fecha
from photos_sync.comprimir import comprimir_carpetas_por_dia

class WorkerThread(QThread):
    """
    Esto es VITAL: Si ejecutas tu código dentro de la GUI, 
    la ventana se congelará. Debes ejecutar el trabajo pesado en un hilo secundario.
    """
    finished = pyqtSignal()
    
    def run(self):
        exportar_metadatos_json()
        organizar_capturas_por_fecha()
        comprimir_carpetas_por_dia()
        self.finished.emit()

# En tu clase VentanaPrincipal, dentro del botón "Ejecutar Todo":
def _ejecutar_pipeline(self):
    self.btn_ejecutar.setEnabled(False) # Deshabilitar para evitar clics dobles
    self.worker = WorkerThread()
    self.worker.finished.connect(lambda: self.btn_ejecutar.setEnabled(True))
    self.worker.start()