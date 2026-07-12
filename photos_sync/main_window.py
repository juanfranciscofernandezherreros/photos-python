# main_window.py — Ventana principal única de la aplicación.
#
# Sustituye al menú de consola (cli.menu_interactivo). Todo el pipeline
# (descargar, organizar, comprimir, resumen) se ejecuta en un hilo
# secundario y su salida (los mismos print() de siempre) se redirige a un
# panel de texto dentro de la propia ventana, en vez de la terminal.
import sys
import traceback
from typing import Callable

from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QProgressBar, QMessageBox, QGroupBox,
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
    """Sustituye a sys.stdout/sys.stderr mientras el pipeline corre: en vez
    de escribir en la terminal, emite una señal Qt con cada fragmento de
    texto para que la ventana lo muestre en su panel de log."""
    texto_emitido = pyqtSignal(str)

    def write(self, texto: str) -> None:
        if texto:
            self.texto_emitido.emit(texto)

    def flush(self) -> None:
        pass


class WorkerPipeline(QThread):
    """Ejecuta una lista de pasos del pipeline en un hilo secundario para
    no congelar la interfaz."""
    terminado = pyqtSignal(bool, str)  # (éxito, mensaje)

    def __init__(self, pasos: list[PasoPipeline]) -> None:
        super().__init__()
        self.pasos = pasos

    def run(self) -> None:
        try:
            with evitar_suspension():
                for nombre, funcion in self.pasos:
                    print(f"\n{'=' * 55}")
                    print(f"⏳ INICIANDO: {nombre}")
                    print("=" * 55)
                    funcion()
            self.terminado.emit(True, "Proceso finalizado correctamente.")
        except Exception:
            print("\n❌ ERROR:\n" + traceback.format_exc())
            self.terminado.emit(False, "El proceso se detuvo por un error. Revisa el log.")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Photos Sync")
        self.setMinimumSize(720, 560)
        self.worker: WorkerPipeline | None = None
        self.ventana_carpetas: SelectorCarpetas | None = None
        self._construir_interfaz()
        self._redirigir_salida()

    # ---------------------------------------------------------- interfaz --
    def _construir_interfaz(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        titulo = QLabel("📱 Photos Sync — Nothing Phone")
        titulo.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(titulo)

        # --- Configuración ---
        grupo_config = QGroupBox("Configuración")
        fila_config = QHBoxLayout(grupo_config)
        btn_carpetas = QPushButton("⚙️ Configurar carpetas de origen/destino")
        btn_carpetas.clicked.connect(self._abrir_selector_carpetas)
        fila_config.addWidget(btn_carpetas)
        layout.addWidget(grupo_config)

        # --- Pasos individuales ---
        grupo_pasos = QGroupBox("Pasos del pipeline")
        fila_pasos = QHBoxLayout(grupo_pasos)
        self.botones_paso: list[QPushButton] = []
        for i, (nombre, _fn) in enumerate(PASOS):
            btn = QPushButton(f"{i + 1}. {nombre.split('(')[0].strip()}")
            btn.clicked.connect(lambda _checked, idx=i: self._ejecutar([PASOS[idx]]))
            fila_pasos.addWidget(btn)
            self.botones_paso.append(btn)
        layout.addWidget(grupo_pasos)

        # --- Ejecutar todo ---
        self.btn_todo = QPushButton("▶ Ejecutar TODO el pipeline")
        self.btn_todo.setStyleSheet("font-weight: bold; padding: 8px;")
        self.btn_todo.clicked.connect(lambda: self._ejecutar(PASOS))
        layout.addWidget(self.btn_todo)

        # --- Botón Cerrar ---
        btn_salir = QPushButton("❌ Finalizar el programa")
        btn_salir.setStyleSheet("background-color: #ff5555; color: white; font-weight: bold;")
        btn_salir.clicked.connect(self.close)
        layout.addWidget(btn_salir)


        # --- Progreso ---
        self.barra_progreso = QProgressBar()
        self.barra_progreso.setRange(0, 0)  # indeterminada
        self.barra_progreso.setVisible(False)
        layout.addWidget(self.barra_progreso)

        self.lbl_estado = QLabel("Listo.")
        layout.addWidget(self.lbl_estado)

        # --- Log ---
        layout.addWidget(QLabel("<b>Registro:</b>"))
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Consolas", 9))
        self.log.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        layout.addWidget(self.log, stretch=1)

    def _redirigir_salida(self) -> None:
        """A partir de aquí, cualquier print() de descargar.py, organizar.py,
        comprimir.py, resumen.py, etc. aparece en el panel de log de la
        ventana en vez de en una terminal."""
        self._flujo = FlujoSalida()
        self._flujo.texto_emitido.connect(self._append_log)
        sys.stdout = self._flujo
        sys.stderr = self._flujo

    # ------------------------------------------------------------ acciones --
    def _abrir_selector_carpetas(self) -> None:
        # Ventana independiente (no modal): así se puede seguir viendo el
        # log mientras se eligen carpetas.
        self.ventana_carpetas = SelectorCarpetas()
        self.ventana_carpetas.show()

    def _ejecutar(self, pasos: list[PasoPipeline]) -> None:
        if self.worker is not None and self.worker.isRunning():
            QMessageBox.warning(self, "Proceso en curso", "Ya hay un paso ejecutándose.")
            return

        self._set_controles_activos(False)
        self.barra_progreso.setVisible(True)
        self.lbl_estado.setText(f"Ejecutando: {', '.join(n for n, _ in pasos)}...")

        self.worker = WorkerPipeline(pasos)
        self.worker.terminado.connect(self._al_terminar)
        self.worker.start()

    def _al_terminar(self, exito: bool, mensaje: str) -> None:
        self.barra_progreso.setVisible(False)
        self._set_controles_activos(True)
        self.lbl_estado.setText(mensaje)
        if exito:
            QMessageBox.information(self, "Completado", mensaje)
        else:
            QMessageBox.critical(self, "Error", mensaje)

    def _set_controles_activos(self, activos: bool) -> None:
        self.btn_todo.setEnabled(activos)
        for btn in self.botones_paso:
            btn.setEnabled(activos)

    def _append_log(self, texto: str) -> None:
        self.log.moveCursor(QTextCursor.MoveOperation.End)
        self.log.insertPlainText(texto)
        self.log.moveCursor(QTextCursor.MoveOperation.End)

    def closeEvent(self, event) -> None:
        # Restaura la salida estándar al cerrar, por si algo más la usa.
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        if self.worker is not None and self.worker.isRunning():
            self.worker.terminate()
        super().closeEvent(event)


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    ventana = MainWindow()
    ventana.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
