# main_window.py — Ventana principal única de la aplicación.
#
# Sustituye al menú de consola (cli.menu_interactivo). Todo el pipeline
# (download, organize, compress, summary) se ejecuta en un hilo
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

from .folder_selector import FolderSelector
from .keep_awake import prevent_sleep
from .flow_layout import FlowLayout
from .web_server import iniciar_servidor_web, WEB_PORT
from . import download, organize, compress, summary, connection, ssh_connection, upload_ssh

PasoPipeline = tuple[str, Callable[[], None]]

PASOS: list[PasoPipeline] = [
    ("Descargar metadatos (móviles/servidores SSH conectados -> JSON)", download.export_metadata_json),
    ("Organizar por fecha (JSON -> agrupado/AAAA/MM/DD)", organize.organize_captures_by_date),
    ("Comprimir por día (agrupado -> .zip)", compress.compress_folders_by_day),
    ("Contar fotos por día (JSON -> summary_por_dia.json)", summary.generate_daily_summary),
    ("Subir organizado a servidor SSH (opcional)", upload_ssh.upload_organized_to_ssh),
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


class ConnectionWorker(QThread):
    """Ejecuta 'net use' (connect o disconnect una unidad) en un hilo
    aparte: si el móvil no responde, el 'net use' puede tardar hasta el
    timeout sin congelar la ventana."""
    terminado = pyqtSignal(bool, str, str, str)  # (éxito, mensaje, letra, accion)

    def __init__(self, accion: str, letra: str, ip: str = "", puerto: str = "") -> None:
        super().__init__()
        self.accion = accion  # "mount" o "unmount"
        self.letra = letra
        self.ip = ip
        self.puerto = puerto

    def run(self) -> None:
        if self.accion == "mount":
            exito, mensaje = connection.mount(self.letra, self.ip, self.puerto)
        else:
            exito, mensaje = connection.unmount(self.letra)
        self.terminado.emit(exito, mensaje, self.letra, self.accion)


class SSHConnectionWorker(QThread):
    """Prueba una conexión SSH/SFTP (connect + listar la ruta remota) en
    un hilo aparte: si el servidor no responde, el intento puede tardar
    hasta el timeout sin congelar la ventana. A diferencia de la unidad
    WebDAV, una conexión SSH no se 'monta': solo se guarda su configuración
    y se abre/cierra cada vez que el pipeline la necesita."""
    terminado = pyqtSignal(bool, str)  # (éxito, mensaje)

    def __init__(self, connection_ssh: ssh_connection.SSHConnection, contrasena: str = "") -> None:
        super().__init__()
        self.connection_ssh = connection_ssh
        self.contrasena = contrasena

    def run(self) -> None:
        exito, mensaje = ssh_connection.SSHClient(self.connection_ssh, contrasena=self.contrasena).test_connection()
        self.terminado.emit(exito, mensaje)


class PipelineWorker(QThread):
    """Ejecuta una lista de pasos del pipeline en un hilo secundario para
    no congelar la interfaz."""
    terminado = pyqtSignal(bool, str)  # (éxito, mensaje)

    def __init__(self, pasos: list[PasoPipeline]) -> None:
        super().__init__()
        self.pasos = pasos

    def run(self) -> None:
        try:
            with prevent_sleep():
                for nombre, funcion in self.pasos:
                    print(f"\n{'=' * 55}")
                    print(f"⏳ STARTING: {nombre}")
                    print("=" * 55)
                    funcion()
            self.terminado.emit(True, "Process completed successfully.")
        except Exception:
            print("\n❌ ERROR:\n" + traceback.format_exc())
            self.terminado.emit(False, "Process stopped due to an error. Check the log.")


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
        self.worker: PipelineWorker | None = None
        self.worker_connection: ConnectionWorker | None = None
        self.worker_ssh: SSHConnectionWorker | None = None
        self.ventana_carpetas: FolderSelector | None = None
        self._build_ui()
        self._redirigir_salida()
        self._refresh_connections()
        self._refresh_connections_ssh()
        # Arrancar servidor web en hilo de fondo
        iniciar_servidor_web()
        print(f"🌐 Open http://localhost:{WEB_PORT} in your browser for the web interface.\n")

    # ---------------------------------------------------------- interfaz --
    def _build_ui(self) -> None:
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
        grupo_connection = QGroupBox("📡 Conexión WebDAV (puedes connect varios móviles a la vez)")
        col_connection = QVBoxLayout(grupo_connection)

        fila_datos = QFormLayout()
        self.combo_letra = QComboBox()
        self.combo_letra.addItems(connection.AVAILABLE_DRIVE_LETTERS)
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

        col_connection.addLayout(fila_datos)

        fila_botones_connection = FlowLayout()
        self.btn_connect = QPushButton("🔗 Conectar")
        self.btn_connect.clicked.connect(self._connect)
        fila_botones_connection.addWidget(self.btn_connect)
        self.btn_disconnect = QPushButton("🔌 Disconnect seleccionada")
        self.btn_disconnect.clicked.connect(self._disconnect)
        fila_botones_connection.addWidget(self.btn_disconnect)
        btn_refresh_connection = QPushButton("🔄 Refrescar estado")
        btn_refresh_connection.clicked.connect(self._refresh_connections)
        fila_botones_connection.addWidget(btn_refresh_connection)
        col_connection.addLayout(fila_botones_connection)

        col_connection.addWidget(QLabel("Móviles conectados/guardados:"))
        self.lista_connections = QListWidget()
        self.lista_connections.setMinimumHeight(70)
        self.lista_connections.setMaximumHeight(120)
        self.lista_connections.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        col_connection.addWidget(self.lista_connections)

        layout.addWidget(grupo_connection)

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
        fila_ssh_2.addRow("Ruta remota (origen):", self.campo_ssh_ruta)

        self.campo_ssh_ruta_destino = QLineEdit()
        self.campo_ssh_ruta_destino.setPlaceholderText(
            "solo si es 'ambos': ruta DISTINTA a la de origen, ej. /home/juan/fotos_organizadas"
        )
        fila_ssh_2.addRow("Ruta remota (destino):", self.campo_ssh_ruta_destino)

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
        self.combo_ssh_rol.addItems(ssh_connection.VALID_ROLES)
        self.combo_ssh_rol.currentTextChanged.connect(self._actualizar_estado_campo_ruta_destino)
        fila_ssh_2.addRow("Usar como:", self.combo_ssh_rol)

        col_ssh.addLayout(fila_ssh_2)
        self._actualizar_estado_campo_ruta_destino(self.combo_ssh_rol.currentText())

        fila_botones_ssh = FlowLayout()
        btn_guardar_ssh = QPushButton("💾 Guardar")
        btn_guardar_ssh.clicked.connect(self._guardar_connection_ssh)
        fila_botones_ssh.addWidget(btn_guardar_ssh)
        self.btn_test_connection_ssh = QPushButton("🔍 Probar conexión")
        self.btn_test_connection_ssh.clicked.connect(self._test_connection_connection_ssh)
        fila_botones_ssh.addWidget(self.btn_test_connection_ssh)
        btn_eliminar_ssh = QPushButton("🗑️ Eliminar seleccionada")
        btn_eliminar_ssh.clicked.connect(self._eliminar_connection_ssh)
        fila_botones_ssh.addWidget(btn_eliminar_ssh)
        col_ssh.addLayout(fila_botones_ssh)

        col_ssh.addWidget(QLabel("Servidores SSH guardados:"))
        self.lista_connections_ssh = QListWidget()
        self.lista_connections_ssh.setMinimumHeight(70)
        self.lista_connections_ssh.setMaximumHeight(120)
        self.lista_connections_ssh.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.lista_connections_ssh.itemClicked.connect(self._cargar_connection_ssh_en_formulario)
        col_ssh.addWidget(self.lista_connections_ssh)

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
        fila_log_header = QHBoxLayout()
        fila_log_header.addWidget(QLabel("<b>Registro:</b>"))
        fila_log_header.addStretch()
        btn_abrir_web = QPushButton(f"🌐 Abrir interfaz web (:{WEB_PORT})")
        btn_abrir_web.clicked.connect(self._abrir_web)
        fila_log_header.addWidget(btn_abrir_web)
        layout.addLayout(fila_log_header)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Consolas", 9))
        self.log.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        self.log.setMinimumHeight(160)
        self.log.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.log, stretch=1)

    def _redirigir_salida(self) -> None:
        """A partir de aquí, cualquier print() de download.py, organize.py,
        compress.py, summary.py, etc. aparece en el panel de log de la
        ventana en vez de en una terminal."""
        self._flujo = FlujoSalida()
        self._flujo.texto_emitido.connect(self._append_log)
        sys.stdout = self._flujo
        sys.stderr = self._flujo

    # -------------------------------------------------------- conexión --
    def _refresh_connections(self) -> None:
        self.lista_connections.clear()
        for c in connection.load_connections():
            montada = connection.is_mounted(c["letra"])
            estado = "🟢 conectada" if montada else "🔴 no disponible ahora"
            texto = f"{c['letra']}  {c.get('alias', '')}  ({c.get('ip')}:{c.get('puerto')})  —  {estado}"
            item = QListWidgetItem(texto)
            item.setData(1000, c["letra"])
            self.lista_connections.addItem(item)

    def _connect(self) -> None:
        if self.worker_connection is not None and self.worker_connection.isRunning():
            QMessageBox.warning(self, "In progress", "A connection is already in progress, please wait.")
            return

        letra = self.combo_letra.currentText()
        ip = self.campo_ip.text().strip()
        puerto = self.campo_puerto.text().strip() or "8080"
        alias = self.campo_alias.text().strip() or letra

        if not ip:
            QMessageBox.warning(self, "Missing IP", "Enter the IP shown in the WebDAV app on your phone.")
            return

        self._alias_pendiente = alias
        self.btn_connect.setEnabled(False)
        self.lbl_estado.setText(f"Connecting {letra} to {ip}:{puerto}...")
        print(f"\n🔗 Running: net use {letra} http://{ip}:{puerto}")

        self.worker_connection = ConnectionWorker("mount", letra, ip, puerto)
        self.worker_connection.terminado.connect(self._al_terminar_connection)
        self.worker_connection.start()

    def _disconnect(self) -> None:
        item = self.lista_connections.currentItem()
        if item is None:
            QMessageBox.information(self, "Nothing selected", "Select a phone from the list first.")
            return
        if self.worker_connection is not None and self.worker_connection.isRunning():
            QMessageBox.warning(self, "In progress", "A connection is already in progress, please wait.")
            return

        letra = item.data(1000)
        self.btn_disconnect.setEnabled(False)
        self.lbl_estado.setText(f"Disconnecting {letra}...")
        print(f"\n🔌 Running: net use {letra} /delete")

        self.worker_connection = ConnectionWorker("unmount", letra)
        self.worker_connection.terminado.connect(self._al_terminar_connection)
        self.worker_connection.start()

    def _al_terminar_connection(self, exito: bool, mensaje: str, letra: str, accion: str) -> None:
        self.btn_connect.setEnabled(True)
        self.btn_disconnect.setEnabled(True)
        print(mensaje)

        if accion == "mount":
            if exito:
                ip = self.campo_ip.text().strip()
                puerto = self.campo_puerto.text().strip() or "8080"
                alias = getattr(self, "_alias_pendiente", letra)
                connection.add_or_update_connection(letra, ip, puerto, alias)
                self.lbl_estado.setText(f"{letra} conectada. Ya puedes usar 'Configurar carpetas' o el pipeline.")
            else:
                self.lbl_estado.setText(f"❌ Could not connect {letra}. Check the log.")
                QMessageBox.critical(self, "Error al connect", mensaje)
        else:  # unmount
            connection.remove_connection(letra)
            self.lbl_estado.setText(mensaje if exito else f"⚠️ {mensaje}")

        self._refresh_connections()

    # ------------------------------------------------------------ SSH --
    def _refresh_connections_ssh(self) -> None:
        self.lista_connections_ssh.clear()
        for c in ssh_connection.load_ssh_connections():
            texto = (f"{c['alias']}  —  {c['usuario']}@{c['host']}:{c['puerto']}  "
                     f"origen='{c['ruta_remota']}'  (rol: {c['rol']})")
            ruta_dest = c.get("ruta_remota_destino")
            if ruta_dest:
                texto += f"  destino='{ruta_dest}'"
            item = QListWidgetItem(texto)
            item.setData(1000, c["alias"])
            self.lista_connections_ssh.addItem(item)

    def _actualizar_estado_campo_ruta_destino(self, rol: str) -> None:
        """La ruta de destino solo tiene sentido si el servidor se usa
        también/solo como destino; para 'origen' la deshabilitamos para
        que quede claro que no se usa."""
        usa_destino = rol in ("destino", "ambos")
        self.campo_ssh_ruta_destino.setEnabled(usa_destino)
        if rol == "ambos":
            self.campo_ssh_ruta_destino.setPlaceholderText(
                "OBLIGATORIA con 'ambos': ruta DISTINTA a la de origen, ej. /home/juan/fotos_organizadas"
            )
        else:
            self.campo_ssh_ruta_destino.setPlaceholderText(
                "opcional: vacío = upload a la misma 'Ruta remota (origen)'"
            )

    def _elegir_clave_ssh(self) -> None:
        ruta, _ = QFileDialog.getOpenFileName(self, "Elegir clave privada SSH")
        if ruta:
            self.campo_ssh_clave.setText(ruta)

    def _leer_formulario_ssh(self) -> ssh_connection.SSHConnection | None:
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
            QMessageBox.warning(self, "Invalid port", "Port must be a number, e.g. 22.")
            return None

        return {
            "alias": alias,
            "host": host,
            "puerto": puerto,
            "usuario": usuario,
            "ruta_remota": ruta_remota,
            "ruta_remota_destino": self.campo_ssh_ruta_destino.text().strip(),
            "clave_privada": self.campo_ssh_clave.text().strip(),
            "rol": self.combo_ssh_rol.currentText(),
        }

    def _guardar_connection_ssh(self) -> None:
        datos = self._leer_formulario_ssh()
        if datos is None:
            return

        try:
            ssh_connection.add_or_update_ssh_connection(
                alias=datos["alias"], host=datos["host"], puerto=datos["puerto"],
                usuario=datos["usuario"], ruta_remota=datos["ruta_remota"],
                clave_privada=datos["clave_privada"], rol=datos["rol"],
                ruta_remota_destino=datos["ruta_remota_destino"],
            )
        except ValueError as e:
            QMessageBox.warning(self, "Configuración no válida", str(e))
            return

        self._refresh_connections_ssh()
        self.lbl_estado.setText(f"SSH connection '{datos['alias']}' saved.")

    def _test_connection_connection_ssh(self) -> None:
        if self.worker_ssh is not None and self.worker_ssh.isRunning():
            QMessageBox.warning(self, "In progress", "An SSH connection test is already running.")
            return
        if not ssh_connection.paramiko_available():
            QMessageBox.critical(
                self, "Missing 'paramiko'",
                "Install the library with: pip install paramiko"
            )
            return

        datos = self._leer_formulario_ssh()
        if datos is None:
            return

        self.btn_test_connection_ssh.setEnabled(False)
        self.lbl_estado.setText(f"Testing SSH connection to {datos['host']}...")
        print(f"\n🔍 Testing SSH connection: {datos['usuario']}@{datos['host']}:{datos['puerto']} "
              f"'{datos['ruta_remota']}'")

        # La contraseña (si se ha escrito) solo se usa para esta prueba
        # puntual: no se guarda en disco en ningún momento.
        self.worker_ssh = SSHConnectionWorker(datos, contrasena=self.campo_ssh_contrasena.text())
        self.worker_ssh.terminado.connect(self._al_terminar_prueba_ssh)
        self.worker_ssh.start()

    def _al_terminar_prueba_ssh(self, exito: bool, mensaje: str) -> None:
        self.btn_test_connection_ssh.setEnabled(True)
        print(mensaje)
        self.lbl_estado.setText(mensaje)
        if not exito:
            QMessageBox.critical(self, "SSH connection error", mensaje)

    def _eliminar_connection_ssh(self) -> None:
        item = self.lista_connections_ssh.currentItem()
        if item is None:
            QMessageBox.information(self, "Nothing selected", "Select a server from the list first.")
            return
        alias = item.data(1000)
        ssh_connection.remove_ssh_connection(alias)
        self._refresh_connections_ssh()
        self.lbl_estado.setText(f"SSH connection '{alias}' removed.")

    def _cargar_connection_ssh_en_formulario(self, item: QListWidgetItem) -> None:
        alias = item.data(1000)
        c = ssh_connection.get_connection(alias)
        if c is None:
            return
        self.campo_ssh_alias.setText(c["alias"])
        self.campo_ssh_host.setText(c["host"])
        self.campo_ssh_puerto.setText(str(c["puerto"]))
        self.campo_ssh_usuario.setText(c["usuario"])
        self.campo_ssh_ruta.setText(c["ruta_remota"])
        self.campo_ssh_ruta_destino.setText(c.get("ruta_remota_destino", ""))
        self.campo_ssh_clave.setText(c["clave_privada"])
        self.combo_ssh_rol.setCurrentText(c["rol"])

    # ------------------------------------------------------------ acciones --
    def _abrir_web(self) -> None:
        import webbrowser
        webbrowser.open(f"http://localhost:{WEB_PORT}")

    def _abrir_selector_carpetas(self) -> None:
        # Ventana independiente (no modal): así se puede seguir viendo el
        # log mientras se eligen carpetas.
        self.ventana_carpetas = FolderSelector()
        self.ventana_carpetas.show()

    def _ejecutar(self, pasos: list[PasoPipeline]) -> None:
        if self.worker is not None and self.worker.isRunning():
            QMessageBox.warning(self, "In progress", "A step is already running.")
            return

        self._set_controles_activos(False)
        self.barra_progreso.setVisible(True)
        self.lbl_estado.setText(f"Running: {', '.join(n for n, _ in pasos)}...")

        self.worker = PipelineWorker(pasos)
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
        # Restaura la salida estándar al close, por si algo más la usa.
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        if self.worker is not None and self.worker.isRunning():
            self.worker.terminate()
        if self.worker_connection is not None and self.worker_connection.isRunning():
            self.worker_connection.terminate()
        super().closeEvent(event)


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    ventana = MainWindow()
    ventana.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
