"""Slim main window — imports tab widgets and wires them together."""
from __future__ import annotations

import sys
from typing import Callable

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QProgressBar, QMessageBox, QGroupBox,
    QScrollArea, QSizePolicy,
)

from .folder_selector import FolderSelector
from .flow_layout import FlowLayout
from .web_server import iniciar_servidor_web, WEB_PORT
from .gui.workers import PipelineWorker, PasoPipeline
from .gui.webdav_tab import WebDAVTab
from .gui.ssh_tab import SSHTab
from .pipeline import download, organize, classify, compress, summary, upload_ssh

PASOS: list[PasoPipeline] = [
    ("Sync & save captures", download.sync_captures),
    ("Organize by date", organize.organize_captures_by_date),
    ("Classify photos", classify.classify_captures),
    ("Compress by day", compress.compress_folders_by_day),
    ("Generate summary", summary.generate_daily_summary),
    ("Upload to SSH", upload_ssh.upload_organized_to_ssh),
]


class _OutputRedirect(QObject):
    text_emitted = pyqtSignal(str)
    def write(self, s: str) -> None:
        if s: self.text_emitted.emit(s)
    def flush(self) -> None: pass


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Photos Sync")
        self.setMinimumSize(420, 480)
        self.resize(820, 640)
        self.worker: PipelineWorker | None = None
        self.ventana_carpetas: FolderSelector | None = None
        self._build_ui()
        self._redirect_output()
        iniciar_servidor_web()
        print(f"🌐 Open http://localhost:{WEB_PORT} in your browser for the web interface.\n")

    def _build_ui(self) -> None:
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setCentralWidget(scroll)
        central = QWidget(); scroll.setWidget(central); layout = QVBoxLayout(central)

        titulo = QLabel("📱 Photos Sync"); titulo.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(titulo)

        self.lbl_estado = QLabel("Ready.")

        # --- Tabs ---
        grp_webdav = QGroupBox("📡 WebDAV Connection")
        vb = QVBoxLayout(grp_webdav); self.webdav_tab = WebDAVTab(self.lbl_estado); vb.addWidget(self.webdav_tab)
        layout.addWidget(grp_webdav)

        grp_ssh = QGroupBox("🐧 SSH Connection")
        vb2 = QVBoxLayout(grp_ssh); self.ssh_tab = SSHTab(self.lbl_estado); vb2.addWidget(self.ssh_tab)
        layout.addWidget(grp_ssh)

        # --- Config ---
        grp_cfg = QGroupBox("Settings")
        fc = FlowLayout(grp_cfg)
        btn_folders = QPushButton("⚙️ Configure folders"); btn_folders.clicked.connect(self._open_folder_selector); fc.addWidget(btn_folders)
        layout.addWidget(grp_cfg)

        # --- Pipeline steps ---
        grp_steps = QGroupBox("Pipeline Steps")
        fs = FlowLayout(grp_steps); self.step_buttons: list[QPushButton] = []
        for i, (name, _) in enumerate(PASOS):
            btn = QPushButton(f"{i+1}. {name}"); btn.clicked.connect(lambda _, idx=i: self._run([PASOS[idx]]))
            fs.addWidget(btn); self.step_buttons.append(btn)
        layout.addWidget(grp_steps)

        self.btn_all = QPushButton("▶ Run ALL"); self.btn_all.setStyleSheet("font-weight:bold;padding:8px;")
        self.btn_all.clicked.connect(lambda: self._run(PASOS)); layout.addWidget(self.btn_all)

        self.progress = QProgressBar(); self.progress.setRange(0,0); self.progress.setVisible(False); layout.addWidget(self.progress)
        layout.addWidget(self.lbl_estado)

        # --- Log ---
        hdr = QHBoxLayout(); hdr.addWidget(QLabel("<b>Log:</b>")); hdr.addStretch()
        btn_web = QPushButton(f"🌐 Open web UI (:{WEB_PORT})"); btn_web.clicked.connect(self._open_web); hdr.addWidget(btn_web)
        layout.addLayout(hdr)
        self.log = QTextEdit(); self.log.setReadOnly(True); self.log.setFont(QFont("Consolas", 9))
        self.log.setStyleSheet("background-color:#1e1e1e;color:#d4d4d4;"); self.log.setMinimumHeight(160)
        self.log.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.log, stretch=1)

    def _redirect_output(self) -> None:
        self._out = _OutputRedirect(); self._out.text_emitted.connect(self._append_log)
        sys.stdout = self._out; sys.stderr = self._out

    def _open_web(self) -> None:
        import webbrowser; webbrowser.open(f"http://localhost:{WEB_PORT}")

    def _open_folder_selector(self) -> None:
        self.ventana_carpetas = FolderSelector(); self.ventana_carpetas.show()

    def _run(self, pasos: list[PasoPipeline]) -> None:
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, "In progress", "A step is already running."); return
        self._set_controls(False); self.progress.setVisible(True)
        self.lbl_estado.setText(f"Running: {', '.join(n for n,_ in pasos)}...")
        self.worker = PipelineWorker(pasos); self.worker.terminado.connect(self._on_done); self.worker.start()

    def _on_done(self, ok: bool, msg: str) -> None:
        self.progress.setVisible(False); self._set_controls(True); self.lbl_estado.setText(msg)
        (QMessageBox.information if ok else QMessageBox.critical)(self, "Done" if ok else "Error", msg)

    def _set_controls(self, enabled: bool) -> None:
        self.btn_all.setEnabled(enabled)
        for btn in self.step_buttons: btn.setEnabled(enabled)

    def _append_log(self, text: str) -> None:
        self.log.moveCursor(QTextCursor.MoveOperation.End); self.log.insertPlainText(text)
        self.log.moveCursor(QTextCursor.MoveOperation.End)

    def closeEvent(self, event) -> None:
        sys.stdout = sys.__stdout__; sys.stderr = sys.__stderr__
        for w in (self.worker,): 
            if w and w.isRunning(): w.terminate()
        super().closeEvent(event)


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion"); ventana = MainWindow(); ventana.show(); sys.exit(app.exec())

if __name__ == "__main__":
    main()
