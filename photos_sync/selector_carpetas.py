from pathlib import Path
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QListWidget, QFileDialog, QGroupBox, QAbstractItemView)
from .carpetas import cargar_carpetas_guardadas, guardar_carpetas, cargar_destino_guardado, guardar_destino

class SelectorCarpetas(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Configuración de Fotos")
        self.setFixedSize(500, 450)
        self.carpetas_origen = cargar_carpetas_guardadas()
        destino_previo = cargar_destino_guardado()
        self.carpeta_destino = Path(destino_previo) if destino_previo else None
        self._construir_interfaz()

    def _construir_interfaz(self):
        w = QWidget(); self.setCentralWidget(w); l = QVBoxLayout(w)
        
        # Destino
        self.lbl = QLabel(str(self.carpeta_destino) if self.carpeta_destino else "Sin destino configurado")
        l.addWidget(QLabel("<b>Carpeta de Destino:</b>")); l.addWidget(self.lbl)
        btn_dest = QPushButton("Elegir Carpeta de Destino"); btn_dest.clicked.connect(self._selec_dest)
        l.addWidget(btn_dest)
        
        # Origen
        self.lista = QListWidget(); l.addWidget(QLabel("<b>Carpetas a escanear:</b>")); l.addWidget(self.lista)
        self.lista.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        btn_add = QPushButton("➕ Añadir Carpeta"); btn_add.clicked.connect(self._add_orig)
        l.addWidget(btn_add)
        btn_del = QPushButton("➖ Quitar seleccionadas"); btn_del.clicked.connect(self._quitar)
        l.addWidget(btn_del)
        
        # Guardar
        btn_save = QPushButton("💾 GUARDAR Y CERRAR"); btn_save.clicked.connect(self.close)
        l.addWidget(btn_save)
        self._refrescar()

    def _refrescar(self):
        self.lista.clear()
        for c in self.carpetas_origen: self.lista.addItem(str(c))

    def _selec_dest(self):
        d = QFileDialog.getExistingDirectory(self, "Seleccionar destino")
        if d: 
            self.carpeta_destino = Path(d)
            self.lbl.setText(d)
            guardar_destino(d) # Se guarda al momento para que no haya error si no existe

    def _add_orig(self):
        d = QFileDialog.getExistingDirectory(self, "Seleccionar origen")
        if d: 
            ruta = Path(d)
            if ruta not in self.carpetas_origen:
                self.carpetas_origen.append(ruta)
                guardar_carpetas(self.carpetas_origen)
                self._refrescar()

    def _quitar(self):
        for item in self.lista.selectedItems():
            ruta = Path(item.text())
            if ruta in self.carpetas_origen: self.carpetas_origen.remove(ruta)
        guardar_carpetas(self.carpetas_origen)
        self._refrescar()


def main() -> None:
    """Punto de entrada independiente: `photos-sync-carpetas` en la terminal,
    o `python -m photos_sync.selector_carpetas`. Abre solo esta ventana,
    sin lanzar el pipeline."""
    import sys
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    ventana = SelectorCarpetas()
    ventana.show()
    app.exec()


if __name__ == "__main__":
    main()