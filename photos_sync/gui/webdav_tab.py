"""WebDAV connection tab widget."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QComboBox, QLineEdit,
    QPushButton, QLabel, QListWidget, QListWidgetItem, QMessageBox,
    QSizePolicy,
)

from ..flow_layout import FlowLayout
from .. import connection
from .workers import ConnectionWorker


class WebDAVTab(QWidget):
    """Panel for connecting/disconnecting Android phones via WebDAV."""

    def __init__(self, status_label: QLabel) -> None:
        super().__init__()
        self.lbl_estado = status_label
        self.worker: ConnectionWorker | None = None
        self._alias_pendiente = ""
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.combo_letra = QComboBox()
        self.combo_letra.addItems(connection.AVAILABLE_DRIVE_LETTERS)
        self.combo_letra.setCurrentText("Z:")
        form.addRow("Drive:", self.combo_letra)
        self.campo_alias = QLineEdit(); self.campo_alias.setPlaceholderText("e.g. Nothing Phone (optional)")
        form.addRow("Phone name:", self.campo_alias)
        self.campo_ip = QLineEdit(); self.campo_ip.setPlaceholderText("e.g. 192.168.1.133")
        form.addRow("IP:", self.campo_ip)
        self.campo_puerto = QLineEdit(); self.campo_puerto.setText("8080")
        form.addRow("Port:", self.campo_puerto)
        layout.addLayout(form)

        btns = FlowLayout()
        self.btn_connect = QPushButton("🔗 Connect"); self.btn_connect.clicked.connect(self._connect); btns.addWidget(self.btn_connect)
        self.btn_disconnect = QPushButton("🔌 Disconnect"); self.btn_disconnect.clicked.connect(self._disconnect); btns.addWidget(self.btn_disconnect)
        btn_refresh = QPushButton("🔄 Refresh"); btn_refresh.clicked.connect(self.refresh); btns.addWidget(btn_refresh)
        layout.addLayout(btns)

        layout.addWidget(QLabel("Connected/saved phones:"))
        self.lista = QListWidget(); self.lista.setMinimumHeight(70); self.lista.setMaximumHeight(120)
        self.lista.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.lista)

    def refresh(self) -> None:
        self.lista.clear()
        for c in connection.load_connections():
            ok = connection.is_mounted(c["letra"])
            text = f"{c['letra']}  {c.get('alias','')}  ({c.get('ip')}:{c.get('puerto')})  —  {'🟢 connected' if ok else '🔴 unavailable'}"
            item = QListWidgetItem(text); item.setData(1000, c["letra"]); self.lista.addItem(item)

    def _connect(self) -> None:
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, "In progress", "A connection is already in progress."); return
        ip = self.campo_ip.text().strip()
        if not ip:
            QMessageBox.warning(self, "Missing IP", "Enter the IP shown in the WebDAV app."); return
        letra = self.combo_letra.currentText()
        puerto = self.campo_puerto.text().strip() or "8080"
        self._alias_pendiente = self.campo_alias.text().strip() or letra
        self.btn_connect.setEnabled(False)
        self.lbl_estado.setText(f"Connecting {letra}...")
        self.worker = ConnectionWorker("mount", letra, ip, puerto)
        self.worker.terminado.connect(self._on_done)
        self.worker.start()

    def _disconnect(self) -> None:
        item = self.lista.currentItem()
        if not item: QMessageBox.information(self, "Nothing selected", "Select a phone first."); return
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, "In progress", "A connection is already in progress."); return
        letra = item.data(1000)
        self.btn_disconnect.setEnabled(False)
        self.lbl_estado.setText(f"Disconnecting {letra}...")
        self.worker = ConnectionWorker("unmount", letra)
        self.worker.terminado.connect(self._on_done)
        self.worker.start()

    def _on_done(self, ok: bool, msg: str, letra: str, action: str) -> None:
        self.btn_connect.setEnabled(True); self.btn_disconnect.setEnabled(True)
        print(msg)
        if action == "mount" and ok:
            connection.add_or_update_connection(letra, self.campo_ip.text().strip(),
                self.campo_puerto.text().strip() or "8080", self._alias_pendiente)
        elif action == "unmount":
            connection.remove_connection(letra)
        self.lbl_estado.setText(msg if ok else f"❌ {msg}")
        self.refresh()
