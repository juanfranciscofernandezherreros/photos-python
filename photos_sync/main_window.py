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
    QComboBox, QLineEdit, QListWidget, QListWidgetItem, QFormLayout,
)

from .selector_carpetas import SelectorCarpetas
from .mantener_despierto import evitar_suspension
from . import descargar, organizar, comprimir, resumen, conexion

PasoPipeline = tuple[str, Callable[[], None]]

PASOS: list[PasoPipeline] = [
    ("Descargar metadatos (móviles conectados -> JSON)", descargar.exportar_metadatos_json),
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


class WorkerConexion(QThread):
    """Ejecuta 'net use' (conectar o desconectar una unidad) en un hilo
    aparte: si el móvil no responde, el 'net use' puede tardar hasta el
    timeout sin congelar la ventana."""
    terminado = pyqtSignal(bool, str, str, str)  # (éxito, mensaje, letra, accion)

    def __init__(self, accion: str, letra: str, ip: str = "", puerto: str = "") -> None:
        super().__init__()
        self.accion = accion  # "montar" o "desmontar"
        self.letra = letra
        self.ip = ip
        self.puerto = puerto

    def run(self) -> None:
        if self.accion == "montar":
            exito, mensaje = conexion.montar(self.letra, self.ip, self.puerto)
        else:
            exito, mensaje = conexion.desmontar(self.letra)
        self.terminado.emit(exito, mensaje, self.letra, self.accion)


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
        self.worker_conexion: WorkerConexion | None = None
        self.ventana_carpetas: SelectorCarpetas | None = None
        self._construir_interfaz()
        self._redirigir_salida()
        self._refrescar_conexiones()

    # ---------------------------------------------------------- interfaz --
    def _construir_interfaz(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        titulo = QLabel("📱 Photos Sync — Nothing Phone")
        titulo.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(titulo)

        # --- Conexión WebDAV (uno o varios móviles) ---
        grupo_conexion = QGroupBox("📡 Conexión WebDAV (puedes conectar varios móviles a la vez)")
        col_conexion = QVBoxLayout(grupo_conexion)

        fila_datos = QFormLayout()
        self.combo_letra = QComboBox()
        self.combo_letra.addItems(conexion.LETRAS_DISPONIBLES)
        self.combo_letra.setCurrentText("Z:")
        fila_datos.addRow("Unidad:", self.combo_letra)

        self.campo_alias = QLineEdit()
        self.campo_alias.setPlaceholderText("ej. Nothing Phone (opcional)")
        fila_datos.addRow("Nombre del móvil:", self.campo_alias)

        self.campo_ip = QLineEdit()
        self.campo_ip.setPlaceholderText("ej. 192.168.1.133")
        fila_datos.addRow("IP:", self.campo_ip)

        self.campo_puerto = QLineEdit()
        self.campo_puerto.setPlaceholderText("8080")
        self.campo_puerto.setText("8080")
        fila_datos.addRow("Puerto:", self.campo_puerto)

        col_conexion.addLayout(fila_datos)

        fila_botones_conexion = QHBoxLayout()
        self.btn_conectar = QPushButton("🔗 Conectar")
        self.btn_conectar.clicked.connect(self._conectar)
        fila_botones_conexion.addWidget(self.btn_conectar)
        self.btn_desconectar = QPushButton("🔌 Desconectar seleccionada")
        self.btn_desconectar.clicked.connect(self._desconectar)
        fila_botones_conexion.addWidget(self.btn_desconectar)
        btn_refrescar_conexion = QPushButton("🔄 Refrescar estado")
        btn_refrescar_conexion.clicked.connect(self._refrescar_conexiones)
        fila_botones_conexion.addWidget(btn_refrescar_conexion)
        col_conexion.addLayout(fila_botones_conexion)

        col_conexion.addWidget(QLabel("Móviles conectados/guardados:"))
        self.lista_conexiones = QListWidget()
        self.lista_conexiones.setMaximumHeight(90)
        col_conexion.addWidget(self.lista_conexiones)

        layout.addWidget(grupo_conexion)

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

    # -------------------------------------------------------- conexión --
    def _refrescar_conexiones(self) -> None:
        self.lista_conexiones.clear()
        for c in conexion.cargar_conexiones():
            montada = conexion.esta_montada(c["letra"])
            estado = "🟢 conectada" if montada else "🔴 no disponible ahora"
            texto = f"{c['letra']}  {c.get('alias', '')}  ({c.get('ip')}:{c.get('puerto')})  —  {estado}"
            item = QListWidgetItem(texto)
            item.setData(1000, c["letra"])
            self.lista_conexiones.addItem(item)

    def _conectar(self) -> None:
        if self.worker_conexion is not None and self.worker_conexion.isRunning():
            QMessageBox.warning(self, "En curso", "Ya hay una conexión en curso, espera a que termine.")
            return

        letra = self.combo_letra.currentText()
        ip = self.campo_ip.text().strip()
        puerto = self.campo_puerto.text().strip() or "8080"
        alias = self.campo_alias.text().strip() or letra

        if not ip:
            QMessageBox.warning(self, "Falta la IP", "Introduce la IP que muestra la app WebDAV del móvil.")
            return

        self._alias_pendiente = alias
        self.btn_conectar.setEnabled(False)
        self.lbl_estado.setText(f"Conectando {letra} a {ip}:{puerto}...")
        print(f"\n🔗 Ejecutando: net use {letra} http://{ip}:{puerto}")

        self.worker_conexion = WorkerConexion("montar", letra, ip, puerto)
        self.worker_conexion.terminado.connect(self._al_terminar_conexion)
        self.worker_conexion.start()

    def _desconectar(self) -> None:
        item = self.lista_conexiones.currentItem()
        if item is None:
            QMessageBox.information(self, "Nada seleccionado", "Selecciona primero un móvil de la lista.")
            return
        if self.worker_conexion is not None and self.worker_conexion.isRunning():
            QMessageBox.warning(self, "En curso", "Ya hay una conexión en curso, espera a que termine.")
            return

        letra = item.data(1000)
        self.btn_desconectar.setEnabled(False)
        self.lbl_estado.setText(f"Desconectando {letra}...")
        print(f"\n🔌 Ejecutando: net use {letra} /delete")

        self.worker_conexion = WorkerConexion("desmontar", letra)
        self.worker_conexion.terminado.connect(self._al_terminar_conexion)
        self.worker_conexion.start()

    def _al_terminar_conexion(self, exito: bool, mensaje: str, letra: str, accion: str) -> None:
        self.btn_conectar.setEnabled(True)
        self.btn_desconectar.setEnabled(True)
        print(mensaje)

        if accion == "montar":
            if exito:
                ip = self.campo_ip.text().strip()
                puerto = self.campo_puerto.text().strip() or "8080"
                alias = getattr(self, "_alias_pendiente", letra)
                conexion.anadir_o_actualizar_conexion(letra, ip, puerto, alias)
                self.lbl_estado.setText(f"{letra} conectada. Ya puedes usar 'Configurar carpetas' o el pipeline.")
            else:
                self.lbl_estado.setText(f"❌ No se pudo conectar {letra}. Revisa el log.")
                QMessageBox.critical(self, "Error al conectar", mensaje)
        else:  # desmontar
            conexion.quitar_conexion(letra)
            self.lbl_estado.setText(mensaje if exito else f"⚠️ {mensaje}")

        self._refrescar_conexiones()

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
        if self.worker_conexion is not None and self.worker_conexion.isRunning():
            self.worker_conexion.terminate()
        super().closeEvent(event)


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    ventana = MainWindow()
    ventana.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
