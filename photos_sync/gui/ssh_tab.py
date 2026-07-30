"""SSH connection management tab widget."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QComboBox, QLineEdit,
    QPushButton, QLabel, QListWidget, QListWidgetItem, QMessageBox,
    QFileDialog, QSizePolicy,
)

from ..flow_layout import FlowLayout
from .. import ssh_connection
from .workers import SSHConnectionWorker


class SSHTab(QWidget):
    """Panel for managing SSH server connections."""

    def __init__(self, status_label: QLabel) -> None:
        super().__init__()
        self.lbl_estado = status_label
        self.worker: SSHConnectionWorker | None = None
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        f1 = QFormLayout()
        self.campo_alias = QLineEdit(); self.campo_alias.setPlaceholderText("e.g. Home NAS"); f1.addRow("Name:", self.campo_alias)
        self.campo_host = QLineEdit(); self.campo_host.setPlaceholderText("e.g. 192.168.1.50"); f1.addRow("Host:", self.campo_host)
        self.campo_puerto = QLineEdit(); self.campo_puerto.setText("22"); f1.addRow("Port:", self.campo_puerto)
        self.campo_usuario = QLineEdit(); self.campo_usuario.setPlaceholderText("e.g. juan"); f1.addRow("User:", self.campo_usuario)
        layout.addLayout(f1)

        f2 = QFormLayout()
        self.campo_ruta = QLineEdit(); self.campo_ruta.setPlaceholderText("e.g. /home/juan/fotos"); f2.addRow("Remote path (source):", self.campo_ruta)
        self.campo_ruta_dest = QLineEdit(); self.campo_ruta_dest.setPlaceholderText("only if role=ambos"); f2.addRow("Remote path (dest):", self.campo_ruta_dest)
        row_key = QHBoxLayout()
        self.campo_clave = QLineEdit(); self.campo_clave.setPlaceholderText("optional: ~/.ssh/id_rsa"); row_key.addWidget(self.campo_clave)
        btn_pick = QPushButton("📁"); btn_pick.clicked.connect(self._pick_key); row_key.addWidget(btn_pick)
        f2.addRow("Private key:", row_key)
        self.campo_password = QLineEdit(); self.campo_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.campo_password.setPlaceholderText("only for testing; never saved"); f2.addRow("Password:", self.campo_password)
        self.combo_rol = QComboBox(); self.combo_rol.addItems(ssh_connection.VALID_ROLES)
        self.combo_rol.currentTextChanged.connect(self._on_role_change); f2.addRow("Use as:", self.combo_rol)
        layout.addLayout(f2)
        self._on_role_change(self.combo_rol.currentText())

        btns = FlowLayout()
        b1 = QPushButton("💾 Save"); b1.clicked.connect(self._save); btns.addWidget(b1)
        self.btn_test = QPushButton("🔍 Test connection"); self.btn_test.clicked.connect(self._test); btns.addWidget(self.btn_test)
        b3 = QPushButton("🗑️ Delete selected"); b3.clicked.connect(self._delete); btns.addWidget(b3)
        layout.addLayout(btns)

        layout.addWidget(QLabel("Saved SSH servers:"))
        self.lista = QListWidget(); self.lista.setMinimumHeight(70); self.lista.setMaximumHeight(120)
        self.lista.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.lista.itemClicked.connect(self._load_into_form)
        layout.addWidget(self.lista)

    def refresh(self) -> None:
        self.lista.clear()
        for c in ssh_connection.load_ssh_connections():
            text = f"{c['alias']}  —  {c['usuario']}@{c['host']}:{c['puerto']}  source='{c['ruta_remota']}' (role: {c['rol']})"
            dest = c.get("ruta_remota_destino"); 
            if dest: text += f"  dest='{dest}'"
            item = QListWidgetItem(text); item.setData(1000, c["alias"]); self.lista.addItem(item)

    def _on_role_change(self, role: str) -> None:
        self.campo_ruta_dest.setEnabled(role in ("destino", "ambos"))
        self.campo_ruta_dest.setPlaceholderText(
            "REQUIRED: different from source" if role == "ambos" else "optional: empty = use source path")

    def _pick_key(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose SSH private key")
        if path: self.campo_clave.setText(path)

    def _read_form(self) -> ssh_connection.SSHConnection | None:
        a, h, u, r = (self.campo_alias.text().strip(), self.campo_host.text().strip(),
                       self.campo_usuario.text().strip(), self.campo_ruta.text().strip())
        if not all([a, h, u, r]):
            QMessageBox.warning(self, "Missing data", "Fill in at least name, host, user, and remote path."); return None
        try: p = int(self.campo_puerto.text().strip() or "22")
        except ValueError: QMessageBox.warning(self, "Invalid port", "Port must be a number."); return None
        return {"alias": a, "host": h, "puerto": p, "usuario": u, "ruta_remota": r,
                "ruta_remota_destino": self.campo_ruta_dest.text().strip(),
                "clave_privada": self.campo_clave.text().strip(), "rol": self.combo_rol.currentText()}

    def _save(self) -> None:
        data = self._read_form()
        if not data: return
        try:
            ssh_connection.add_or_update_ssh_connection(
                alias=data["alias"], host=data["host"], puerto=data["puerto"],
                usuario=data["usuario"], ruta_remota=data["ruta_remota"],
                clave_privada=data["clave_privada"], rol=data["rol"],
                ruta_remota_destino=data["ruta_remota_destino"])
        except ValueError as e:
            QMessageBox.warning(self, "Invalid config", str(e)); return
        self.refresh(); self.lbl_estado.setText(f"SSH connection '{data['alias']}' saved.")

    def _test(self) -> None:
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, "In progress", "A test is already running."); return
        if not ssh_connection.paramiko_available():
            QMessageBox.critical(self, "Missing paramiko", "pip install paramiko"); return
        data = self._read_form()
        if not data: return
        self.btn_test.setEnabled(False); self.lbl_estado.setText(f"Testing {data['host']}...")
        self.worker = SSHConnectionWorker(data, contrasena=self.campo_password.text())
        self.worker.terminado.connect(self._on_test_done); self.worker.start()

    def _on_test_done(self, ok: bool, msg: str) -> None:
        self.btn_test.setEnabled(True); print(msg); self.lbl_estado.setText(msg)
        if not ok: QMessageBox.critical(self, "SSH error", msg)

    def _delete(self) -> None:
        item = self.lista.currentItem()
        if not item: QMessageBox.information(self, "Nothing selected", "Select a server first."); return
        alias = item.data(1000); ssh_connection.remove_ssh_connection(alias)
        self.refresh(); self.lbl_estado.setText(f"SSH connection '{alias}' removed.")

    def _load_into_form(self, item: QListWidgetItem) -> None:
        c = ssh_connection.get_connection(item.data(1000))
        if not c: return
        self.campo_alias.setText(c["alias"]); self.campo_host.setText(c["host"])
        self.campo_puerto.setText(str(c["puerto"])); self.campo_usuario.setText(c["usuario"])
        self.campo_ruta.setText(c["ruta_remota"]); self.campo_ruta_dest.setText(c.get("ruta_remota_destino", ""))
        self.campo_clave.setText(c["clave_privada"]); self.combo_rol.setCurrentText(c["rol"])
