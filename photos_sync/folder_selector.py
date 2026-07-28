from pathlib import Path
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QPushButton,
                             QLabel, QListWidget, QFileDialog, QGroupBox, QAbstractItemView,
                             QInputDialog, QMessageBox, QSizePolicy)
from .flow_layout import FlowLayout
from .folders import load_saved_folders, save_folders, load_saved_destination, save_destination, save_ssh_destination
from . import ssh_connection

class FolderSelector(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Photo Settings")
        # Tamaño mínimo, no fijo: la ventana ahora se puede redimensionar y
        # los widgets (lista de carpetas, botones) se adaptan al espacio
        # disponible en lugar de quedar recortados o con huecos vacíos.
        self.setMinimumSize(380, 400)
        self.resize(500, 480)
        self.carpetas_origen = load_saved_folders()
        destino_previo = load_saved_destination()
        self.carpeta_destino = Path(destino_previo) if destino_previo else None
        self._build_ui()

    def _build_ui(self):
        w = QWidget(); self.setCentralWidget(w); l = QVBoxLayout(w)
        
        # Destino
        self.lbl = QLabel(str(self.carpeta_destino) if self.carpeta_destino else "No destination configured")
        self.lbl.setWordWrap(True)
        l.addWidget(QLabel("<b>Destination Folder:</b>")); l.addWidget(self.lbl)
        fila_destino = FlowLayout()
        btn_dest = QPushButton("📁 Local folder"); btn_dest.clicked.connect(self._select_dest)
        fila_destino.addWidget(btn_dest)
        btn_dest_ssh = QPushButton("🐧 Saved SSH server"); btn_dest_ssh.clicked.connect(self._select_dest_ssh)
        fila_destino.addWidget(btn_dest_ssh)
        l.addLayout(fila_destino)
        
        # Origen
        self.lista = QListWidget(); l.addWidget(QLabel("<b>Folders to scan:</b>")); l.addWidget(self.lista, stretch=1)
        self.lista.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.lista.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        fila_botones_origen = FlowLayout()
        btn_add = QPushButton("➕ Add Folder"); btn_add.clicked.connect(self._add_source)
        fila_botones_origen.addWidget(btn_add)
        btn_del = QPushButton("➖ Remove selected"); btn_del.clicked.connect(self._remove)
        fila_botones_origen.addWidget(btn_del)
        l.addLayout(fila_botones_origen)
        
        # Guardar
        btn_save = QPushButton("💾 SAVE AND CLOSE"); btn_save.clicked.connect(self.close)
        l.addWidget(btn_save)
        self._refresh()

    def _refresh(self):
        self.lista.clear()
        for c in self.carpetas_origen: self.lista.addItem(str(c))

    def _select_dest(self):
        d = QFileDialog.getExistingDirectory(self, "Select destination")
        if d: 
            self.carpeta_destino = Path(d)
            self.lbl.setText(d)
            save_destination(d)

    def _select_dest_ssh(self):
        alias_disponibles = [c["alias"] for c in ssh_connection.load_ssh_connections()]
        if not alias_disponibles:
            QMessageBox.information(
                self, "No SSH servers",
                "You haven't saved any SSH connections yet. Add one from the "
                "'🐧 SSH Connection' panel in the main window."
            )
            return

        alias, ok = QInputDialog.getItem(
            self, "SSH server as destination", "Choose a server:", alias_disponibles, 0, False
        )
        if ok and alias:
            save_ssh_destination(alias)
            self.lbl.setText(f"🐧 SSH Server: {alias} (local organization stays the same; "
                              f"'Upload to SSH' copies the organized files to this server)")

    def _add_source(self):
        d = QFileDialog.getExistingDirectory(self, "Select source folder")
        if d: 
            ruta = Path(d)
            if ruta not in self.carpetas_origen:
                self.carpetas_origen.append(ruta)
                save_folders(self.carpetas_origen)
                self._refresh()

    def _remove(self):
        for item in self.lista.selectedItems():
            ruta = Path(item.text())
            if ruta in self.carpetas_origen: self.carpetas_origen.remove(ruta)
        save_folders(self.carpetas_origen)
        self._refresh()


def main() -> None:
    """Punto de entrada independiente: `photos-sync-carpetas` en la terminal,
    o `python -m photos_sync.selector_carpetas`. Abre solo esta ventana,
    sin lanzar el pipeline."""
    import sys
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    ventana = FolderSelector()
    ventana.show()
    app.exec()


if __name__ == "__main__":
    main()