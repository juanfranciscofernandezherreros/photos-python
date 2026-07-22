from pathlib import Path
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QPushButton,
                             QLabel, QListWidget, QFileDialog, QGroupBox, QAbstractItemView,
                             QInputDialog, QMessageBox, QSizePolicy)
from .flow_layout import FlowLayout
from .carpetas import cargar_carpetas_guardadas, guardar_carpetas, cargar_destino_guardado, guardar_destino, guardar_destino_ssh
from . import ssh_conexion

class SelectorCarpetas(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Configuración de Fotos")
        # Tamaño mínimo, no fijo: la ventana ahora se puede redimensionar y
        # los widgets (lista de carpetas, botones) se adaptan al espacio
        # disponible en lugar de quedar recortados o con huecos vacíos.
        self.setMinimumSize(380, 400)
        self.resize(500, 480)
        self.carpetas_origen = cargar_carpetas_guardadas()
        destino_previo = cargar_destino_guardado()
        self.carpeta_destino = Path(destino_previo) if destino_previo else None
        self._construir_interfaz()

    def _construir_interfaz(self):
        w = QWidget(); self.setCentralWidget(w); l = QVBoxLayout(w)
        
        # Destino
        self.lbl = QLabel(str(self.carpeta_destino) if self.carpeta_destino else "Sin destino configurado")
        self.lbl.setWordWrap(True)
        l.addWidget(QLabel("<b>Carpeta de Destino:</b>")); l.addWidget(self.lbl)
        fila_destino = FlowLayout()
        btn_dest = QPushButton("📁 Carpeta local"); btn_dest.clicked.connect(self._selec_dest)
        fila_destino.addWidget(btn_dest)
        btn_dest_ssh = QPushButton("🐧 Servidor SSH guardado"); btn_dest_ssh.clicked.connect(self._selec_dest_ssh)
        fila_destino.addWidget(btn_dest_ssh)
        l.addLayout(fila_destino)
        
        # Origen
        self.lista = QListWidget(); l.addWidget(QLabel("<b>Carpetas a escanear:</b>")); l.addWidget(self.lista, stretch=1)
        self.lista.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.lista.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        fila_botones_origen = FlowLayout()
        btn_add = QPushButton("➕ Añadir Carpeta"); btn_add.clicked.connect(self._add_orig)
        fila_botones_origen.addWidget(btn_add)
        btn_del = QPushButton("➖ Quitar seleccionadas"); btn_del.clicked.connect(self._quitar)
        fila_botones_origen.addWidget(btn_del)
        l.addLayout(fila_botones_origen)
        
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

    def _selec_dest_ssh(self):
        alias_disponibles = [c["alias"] for c in ssh_conexion.cargar_conexiones_ssh()]
        if not alias_disponibles:
            QMessageBox.information(
                self, "Sin servidores SSH",
                "Todavía no has guardado ninguna conexión SSH. Añade una desde el panel "
                "'🐧 Conexión SSH' de la ventana principal."
            )
            return

        alias, ok = QInputDialog.getItem(
            self, "Servidor SSH como destino", "Elige un servidor:", alias_disponibles, 0, False
        )
        if ok and alias:
            guardar_destino_ssh(alias)
            self.lbl.setText(f"🐧 Servidor SSH: {alias} (la organización local sigue igual; "
                              f"'Subir a SSH' copia después lo organizado a este servidor)")

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