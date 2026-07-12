# main_window.py — Ventana principal única de la aplicación.
import sys
import traceback
import subprocess
from typing import Callable

from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QProgressBar, QMessageBox, QGroupBox, 
    QLineEdit, QComboBox
)

from .selector_carpetas import SelectorCarpetas
from .mantener_despierto import evitar_suspension
from . import descargar, organizar, comprimir, resumen

PasoPipeline = tuple[str, Callable[[], None]]

PASOS: list[PasoPipeline] = [
    ("Descargar metadatos (Z: -> JSON)", descargar.exportar_metadatos_json),
    ("Organizar por fecha (JSON -> agrupado/AAAA/MM/DD)", organizar.organizar_capturas_por_fecha),
    ("Comprimir por día (agrupado -> .zip)", comprimir.comprimir_carpetas_por_dia),
    ("Contar fotos por día (JSON -> resumen_por_dia.json)", resumen.generar_resumen_por_dia),
]

class FlujoSalida(QObject):
    texto_emitido = pyqtSignal(str)
    def write(self, texto: str) -> None:
        if texto: self.texto_emitido.emit(texto)
    def flush(self) -> None: pass

class WorkerPipeline(QThread):
    terminado = pyqtSignal(bool, str)
    def __init__(self, pasos: list[PasoPipeline]) -> None:
        super().__init__()
        self.pasos = pasos
    def run(self) -> None:
        try:
            with evitar_suspension():
                for nombre, funcion in self.pasos:
                    print(f"\n{'=' * 55}\n⏳ INICIANDO: {nombre}\n{'=' * 55}")
                    funcion()
            self.terminado.emit(True, "Proceso finalizado correctamente.")
        except Exception:
            print("\n❌ ERROR:\n" + traceback.format_exc())
            self.terminado.emit(False, "El proceso se detuvo por un error.")

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Photos Sync")
        self.setMinimumSize(720, 650)
        self.worker: WorkerPipeline | None = None
        self.ventana_carpetas: SelectorCarpetas | None = None
        self._construir_interfaz()
        self._redirigir_salida()

    def _construir_interfaz(self) -> None:
        central = QWidget(); self.setCentralWidget(central); layout = QVBoxLayout(central)

        # --- Conexión WebDAV ---
        grupo_con = QGroupBox("1. Conexión WebDAV (net use)")
        fila_con = QHBoxLayout(grupo_con)
        self.input_url = QLineEdit("192.168.1.133"); self.input_url.setPlaceholderText("IP")
        self.input_port = QLineEdit("8080"); self.input_port.setPlaceholderText("Puerto")
        self.combo_unidad = QComboBox(); self.combo_unidad.addItems(["Z:", "Y:", "X:"])
        btn_con = QPushButton("🔗 Conectar / Reconectar"); btn_con.clicked.connect(self._ejecutar_net_use)
        fila_con.addWidget(QLabel("IP:")); fila_con.addWidget(self.input_url)
        fila_con.addWidget(QLabel("Port:")); fila_con.addWidget(self.input_port)
        fila_con.addWidget(QLabel("Unidad:")); fila_con.addWidget(self.combo_unidad)
        fila_con.addWidget(btn_con)
        layout.addWidget(grupo_con)

        # --- Configuración ---
        grupo_config = QGroupBox("2. Configuración")
        btn_carpetas = QPushButton("⚙️ Configurar carpetas de origen/destino")
        btn_carpetas.clicked.connect(self._abrir_selector_carpetas)
        QHBoxLayout(grupo_config).addWidget(btn_carpetas)
        layout.addWidget(grupo_config)

        # --- Pasos del pipeline ---
        grupo_pasos = QGroupBox("3. Pipeline")
        fila_pasos = QHBoxLayout(grupo_pasos)
        self.botones_paso: list[QPushButton] = []
        for i, (nombre, _) in enumerate(PASOS):
            btn = QPushButton(f"{i + 1}. {nombre.split('(')[0].strip()}")
            btn.clicked.connect(lambda _, idx=i: self._ejecutar([PASOS[idx]]))
            fila_pasos.addWidget(btn); self.botones_paso.append(btn)
        layout.addWidget(grupo_pasos)

        self.btn_todo = QPushButton("▶ Ejecutar TODO el pipeline"); self.btn_todo.clicked.connect(lambda: self._ejecutar(PASOS))
        layout.addWidget(self.btn_todo)

        # --- Progreso y Log ---
        self.barra_progreso = QProgressBar(); self.barra_progreso.setVisible(False); layout.addWidget(self.barra_progreso)
        self.lbl_estado = QLabel("Listo."); layout.addWidget(self.lbl_estado)
        self.log = QTextEdit(); self.log.setReadOnly(True)
        self.log.setFont(QFont("Consolas", 9)); self.log.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        layout.addWidget(QLabel("<b>Registro:</b>")); layout.addWidget(self.log, stretch=1)

    def _ejecutar_net_use(self) -> None:
        unidad = self.combo_unidad.currentText()
        url = f"http://{self.input_url.text()}:{self.input_port.text()}"
        subprocess.run(["net", "use", unidad, "/delete", "/y"], capture_output=True)
        res = subprocess.run(["net", "use", unidad, url], capture_output=True, text=True)
        if res.returncode == 0:
            QMessageBox.information(self, "Éxito", f"Unidad {unidad} montada con éxito.")
        else:
            QMessageBox.critical(self, "Error de conexión", f"Detalles:\n{res.stderr}")

    def _redirigir_salida(self) -> None:
        self._flujo = FlujoSalida()
        self._flujo.texto_emitido.connect(self._append_log)
        sys.stdout = self._flujo; sys.stderr = self._flujo

    def _ejecutar(self, pasos: list[PasoPipeline]) -> None:
        self.btn_todo.setEnabled(False); self.barra_progreso.setVisible(True)
        self.worker = WorkerPipeline(pasos); self.worker.terminado.connect(self._al_terminar); self.worker.start()

    def _al_terminar(self, exito: bool, mensaje: str) -> None:
        self.barra_progreso.setVisible(False); self.btn_todo.setEnabled(True); self.lbl_estado.setText(mensaje)
        if not exito: QMessageBox.critical(self, "Error", mensaje)

    def _append_log(self, texto: str) -> None:
        self.log.moveCursor(QTextCursor.MoveOperation.End); self.log.insertPlainText(texto)
        self.log.moveCursor(QTextCursor.MoveOperation.End)

    def _abrir_selector_carpetas(self) -> None:
        self.ventana_carpetas = SelectorCarpetas(); self.ventana_carpetas.show()

def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    ventana = MainWindow(); ventana.show(); sys.exit(app.exec())

if __name__ == "__main__":
    main()