# gui.py (The new orchestrator)
from PyQt6.QtCore import QThread, pyqtSignal
from photos_sync.download import export_metadata_json
from photos_sync.organize import organize_captures_by_date
from photos_sync.compress import compress_folders_by_day

class WorkerThread(QThread):
    """
    This is VITAL: If you run your code inside the GUI,
    the window will freeze. You must run heavy work in a secondary thread.
    """
    finished = pyqtSignal()
    
    def run(self):
        export_metadata_json()
        organize_captures_by_date()
        compress_folders_by_day()
        self.finished.emit()

# In your MainWindow class, inside the "Run All" button:
def _ejecutar_pipeline(self):
    self.btn_ejecutar.setEnabled(False) # Deshabilitar para evitar clics dobles
    self.worker = WorkerThread()
    self.worker.finished.connect(lambda: self.btn_ejecutar.setEnabled(True))
    self.worker.start()