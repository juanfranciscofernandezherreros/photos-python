# main_window.py — Ventana principal única de la aplicación.
#
# Sustituye al menú de consola (cli.menu_interactivo). Todo el pipeline
# (descargar, organizar, comprimir, resumen) se ejecuta en un hilo
# secundario y su salida (los mismos print() de siempre) se redirige a un
# panel de texto dentro de la propia ventana, en vez de la terminal.
import sys
import traceback
from typing import Callable

from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QProgressBar, QMessageBox, QGroupBox,
    QComboBox, QLineEdit, QListWidget, QListWidgetItem, QFormLayout, QFileDialog,
    QScrollArea, QSizePolicy,
)

from .selector_carpetas import SelectorCarpetas
from .mantener_despierto import evitar_suspension
from .flow_layout import FlowLayout
from . import descargar, organizar, comprimir, resumen, conexion, ssh_conexion, subir_ssh

PasoPipeline = tuple[str, Callable[[], None]]

PASOS: list[PasoPipeline] = [
    ("Descargar metadatos (móviles/servidores SSH conectados -> JSON)", descargar.exportar_metadatos_json),
    ("Organizar por fecha (JSON -> agrupado/AAAA/MM/DD)", organizar.organizar_capturas_por_fecha),
    ("Comprimir por día (agrupado -> .zip)", comprimir.comprimir_carpetas_por_dia),
    ("Contar fotos por día (JSON -> resumen_por_dia.json)", resumen.generar_resumen_por_dia),
    ("Subir organizado a servidor SSH (opcional)", subir_ssh.subir_organizado_a_ssh),
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


class WorkerConexionSSH(QThread):
    """Prueba una conexión SSH/SFTP (conectar + listar la ruta remota) en
    un hilo aparte: si el servidor no responde, el intento puede tardar
    hasta el timeout sin congelar la ventana. A diferencia de la unidad
    WebDAV, una conexión SSH no se 'monta': solo se guarda su configuración
    y se abre/cierra cada vez que el pipeline la necesita."""
    terminado = pyqtSignal(bool, str)  # (éxito, mensaje)

    def __init__(self, conexion_ssh: ssh_conexion.ConexionSSH, contrasena: str = "") -> None:
        super().__init__()
        self.conexion_ssh = conexion_ssh
        self.contrasena = contrasena

    def run(self) -> None:
        exito, mensaje = ssh_conexion.ClienteSSH(self.conexion_ssh, contrasena=self.contrasena).probar()
        self.terminado.emit(exito, mensaje)


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
        # Tamaño mínimo pequeño: la ventana es responsive (se adapta a
        # pantallas y ventanas más estrechas gracias al QScrollArea y al
        # FlowLayout de los botones), así que no necesitamos imponer un
        # ancho/alto grande de partida.
        self.setMinimumSize(420, 480)
        self.resize(820, 640)
        self.worker: WorkerPipeline | None = None
        self.worker_conexion: WorkerConexion | None = None
        self.worker_ssh: WorkerConexionSSH | None = None
        self.ventana_carpetas: SelectorCarpetas | None = None
        self._construir_interfaz()
        self._redirigir_salida()
        self._refrescar_conexiones()
        self._refrescar_conexiones_ssh()

    # ---------------------------------------------------------- interfaz --
    def _construir_interfaz(self) -> None:
        # El contenido real vive dentro de un QScrollArea: si la ventana se
        # hace más pequeña que el contenido (pantallas chicas, portátiles,
        # o simplemente redimensionar a mano), aparece una barra de scroll
        # en vez de recortar o deformar los controles.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setCentralWidget(scroll)

        central = QWidget()
        scroll.setWidget(central)
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

        fila_botones_conexion = FlowLayout()
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
        self.lista_conexiones.setMinimumHeight(70)
        self.lista_conexiones.setMaximumHeight(120)
        self.lista_conexiones.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        col_conexion.addWidget(self.lista_conexiones)

        layout.addWidget(grupo_conexion)

        # --- Conexión SSH (uno o varios servidores Linux) ---
        grupo_ssh = QGroupBox("🐧 Conexión SSH (servidor Linux, origen y/o destino)")
        col_ssh = QVBoxLayout(grupo_ssh)

        fila_ssh_1 = QFormLayout()
        self.campo_ssh_alias = QLineEdit()
        self.campo_ssh_alias.setPlaceholderText("ej. NAS de casa")
        fila_ssh_1.addRow("Nombre:", self.campo_ssh_alias)

        self.campo_ssh_host = QLineEdit()
        self.campo_ssh_host.setPlaceholderText("ej. 192.168.1.50 o midominio.com")
        fila_ssh_1.addRow("Host:", self.campo_ssh_host)

        self.campo_ssh_puerto = QLineEdit()
        self.campo_ssh_puerto.setText("22")
        fila_ssh_1.addRow("Puerto:", self.campo_ssh_puerto)

        self.campo_ssh_usuario = QLineEdit()
        self.campo_ssh_usuario.setPlaceholderText("ej. juan")
        fila_ssh_1.addRow("Usuario:", self.campo_ssh_usuario)

        col_ssh.addLayout(fila_ssh_1)

        fila_ssh_2 = QFormLayout()
        self.campo_ssh_ruta = QLineEdit()
        self.campo_ssh_ruta.setPlaceholderText("ej. /home/juan/fotos")
        fila_ssh_2.addRow("Ruta remota:", self.campo_ssh_ruta)

        fila_clave = QHBoxLayout()
        self.campo_ssh_clave = QLineEdit()
        self.campo_ssh_clave.setPlaceholderText("opcional: ruta a clave privada, ej. ~/.ssh/id_rsa")
        fila_clave.addWidget(self.campo_ssh_clave)
        btn_elegir_clave = QPushButton("📁")
        btn_elegir_clave.setToolTip("Elegir fichero de clave privada")
        btn_elegir_clave.clicked.connect(self._elegir_clave_ssh)
        fila_clave.addWidget(btn_elegir_clave)
        fila_ssh_2.addRow("Clave privada:", fila_clave)

        self.campo_ssh_contrasena = QLineEdit()
        self.campo_ssh_contrasena.setEchoMode(QLineEdit.EchoMode.Password)
        self.campo_ssh_contrasena.setPlaceholderText("solo para 'Probar conexión'; no se guarda en disco")
        fila_ssh_2.addRow("Contraseña:", self.campo_ssh_contrasena)

        self.combo_ssh_rol = QComboBox()
        self.combo_ssh_rol.addItems(ssh_conexion.ROLES_VALIDOS)
        fila_ssh_2.addRow("Usar como:", self.combo_ssh_rol)

        col_ssh.addLayout(fila_ssh_2)

        fila_botones_ssh = FlowLayout()
        btn_guardar_ssh = QPushButton("💾 Guardar")
        btn_guardar_ssh.clicked.connect(self._guardar_conexion_ssh)
        fila_botones_ssh.addWidget(btn_guardar_ssh)
        self.btn_probar_ssh = QPushButton("🔍 Probar conexión")
        self.btn_probar_ssh.clicked.connect(self._probar_conexion_ssh)
        fila_botones_ssh.addWidget(self.btn_probar_ssh)
        btn_eliminar_ssh = QPushButton("🗑️ Eliminar seleccionada")
        btn_eliminar_ssh.clicked.connect(self._eliminar_conexion_ssh)
        fila_botones_ssh.addWidget(btn_eliminar_ssh)
        col_ssh.addLayout(fila_botones_ssh)

        col_ssh.addWidget(QLabel("Servidores SSH guardados:"))
        self.lista_conexiones_ssh = QListWidget()
        self.lista_conexiones_ssh.setMinimumHeight(70)
        self.lista_conexiones_ssh.setMaximumHeight(120)
        self.lista_conexiones_ssh.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.lista_conexiones_ssh.itemClicked.connect(self._cargar_conexion_ssh_en_formulario)
        col_ssh.addWidget(self.lista_conexiones_ssh)

        layout.addWidget(grupo_ssh)

        # --- Configuración ---
        grupo_config = QGroupBox("Configuración")
        fila_config = FlowLayout(grupo_config)
        btn_carpetas = QPushButton("⚙️ Configurar carpetas de origen/destino")
        btn_carpetas.clicked.connect(self._abrir_selector_carpetas)
        fila_config.addWidget(btn_carpetas)
        layout.addWidget(grupo_config)

        # --- Pasos individuales ---
        grupo_pasos = QGroupBox("Pasos del pipeline")
        fila_pasos = FlowLayout(grupo_pasos)
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
        self.log.setMinimumHeight(160)
        self.log.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
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

    # ------------------------------------------------------------ SSH --
    def _refrescar_conexiones_ssh(self) -> None:
        self.lista_conexiones_ssh.clear()
        for c in ssh_conexion.cargar_conexiones_ssh():
            texto = (f"{c['alias']}  —  {c['usuario']}@{c['host']}:{c['puerto']}  "
                     f"'{c['ruta_remota']}'  (rol: {c['rol']})")
            item = QListWidgetItem(texto)
            item.setData(1000, c["alias"])
            self.lista_conexiones_ssh.addItem(item)

    def _elegir_clave_ssh(self) -> None:
        ruta, _ = QFileDialog.getOpenFileName(self, "Elegir clave privada SSH")
        if ruta:
            self.campo_ssh_clave.setText(ruta)

    def _leer_formulario_ssh(self) -> ssh_conexion.ConexionSSH | None:
        alias = self.campo_ssh_alias.text().strip()
        host = self.campo_ssh_host.text().strip()
        usuario = self.campo_ssh_usuario.text().strip()
        ruta_remota = self.campo_ssh_ruta.text().strip()

        if not (alias and host and usuario and ruta_remota):
            QMessageBox.warning(
                self, "Faltan datos",
                "Rellena al menos nombre, host, usuario y ruta remota."
            )
            return None

        try:
            puerto = int(self.campo_ssh_puerto.text().strip() or "22")
        except ValueError:
            QMessageBox.warning(self, "Puerto no válido", "El puerto debe ser un número, ej. 22.")
            return None

        return {
            "alias": alias,
            "host": host,
            "puerto": puerto,
            "usuario": usuario,
            "ruta_remota": ruta_remota,
            "clave_privada": self.campo_ssh_clave.text().strip(),
            "rol": self.combo_ssh_rol.currentText(),
        }

    def _guardar_conexion_ssh(self) -> None:
        datos = self._leer_formulario_ssh()
        if datos is None:
            return

        ssh_conexion.anadir_o_actualizar_conexion_ssh(
            alias=datos["alias"], host=datos["host"], puerto=datos["puerto"],
            usuario=datos["usuario"], ruta_remota=datos["ruta_remota"],
            clave_privada=datos["clave_privada"], rol=datos["rol"],
        )
        self._refrescar_conexiones_ssh()
        self.lbl_estado.setText(f"Conexión SSH '{datos['alias']}' guardada.")

    def _probar_conexion_ssh(self) -> None:
        if self.worker_ssh is not None and self.worker_ssh.isRunning():
            QMessageBox.warning(self, "En curso", "Ya hay una prueba de conexión SSH en curso.")
            return
        if not ssh_conexion.paramiko_disponible():
            QMessageBox.critical(
                self, "Falta 'paramiko'",
                "Instala la librería con: pip install paramiko"
            )
            return

        datos = self._leer_formulario_ssh()
        if datos is None:
            return

        self.btn_probar_ssh.setEnabled(False)
        self.lbl_estado.setText(f"Probando conexión SSH con {datos['host']}...")
        print(f"\n🔍 Probando conexión SSH: {datos['usuario']}@{datos['host']}:{datos['puerto']} "
              f"'{datos['ruta_remota']}'")

        # La contraseña (si se ha escrito) solo se usa para esta prueba
        # puntual: no se guarda en disco en ningún momento.
        self.worker_ssh = WorkerConexionSSH(datos, contrasena=self.campo_ssh_contrasena.text())
        self.worker_ssh.terminado.connect(self._al_terminar_prueba_ssh)
        self.worker_ssh.start()

    def _al_terminar_prueba_ssh(self, exito: bool, mensaje: str) -> None:
        self.btn_probar_ssh.setEnabled(True)
        print(mensaje)
        self.lbl_estado.setText(mensaje)
        if not exito:
            QMessageBox.critical(self, "Error de conexión SSH", mensaje)

    def _eliminar_conexion_ssh(self) -> None:
        item = self.lista_conexiones_ssh.currentItem()
        if item is None:
            QMessageBox.information(self, "Nada seleccionado", "Selecciona primero un servidor de la lista.")
            return
        alias = item.data(1000)
        ssh_conexion.quitar_conexion_ssh(alias)
        self._refrescar_conexiones_ssh()
        self.lbl_estado.setText(f"Conexión SSH '{alias}' eliminada.")

    def _cargar_conexion_ssh_en_formulario(self, item: QListWidgetItem) -> None:
        alias = item.data(1000)
        c = ssh_conexion.obtener_conexion(alias)
        if c is None:
            return
        self.campo_ssh_alias.setText(c["alias"])
        self.campo_ssh_host.setText(c["host"])
        self.campo_ssh_puerto.setText(str(c["puerto"]))
        self.campo_ssh_usuario.setText(c["usuario"])
        self.campo_ssh_ruta.setText(c["ruta_remota"])
        self.campo_ssh_clave.setText(c["clave_privada"])
        self.combo_ssh_rol.setCurrentText(c["rol"])

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
