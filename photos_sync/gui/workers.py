"""Background QThread workers for the GUI."""
import traceback
from typing import Callable

from PyQt6.QtCore import QThread, pyqtSignal

from ..keep_awake import prevent_sleep
from .. import connection, ssh_connection

PasoPipeline = tuple[str, Callable[[], None]]


class PipelineWorker(QThread):
    """Runs pipeline steps in a background thread."""
    terminado = pyqtSignal(bool, str)

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


class ConnectionWorker(QThread):
    """Runs 'net use' mount/unmount in a background thread."""
    terminado = pyqtSignal(bool, str, str, str)

    def __init__(self, accion: str, letra: str, ip: str = "", puerto: str = "") -> None:
        super().__init__()
        self.accion = accion
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
    """Tests an SSH/SFTP connection in a background thread."""
    terminado = pyqtSignal(bool, str)

    def __init__(self, conn: ssh_connection.SSHConnection, contrasena: str = "") -> None:
        super().__init__()
        self.conn = conn
        self.contrasena = contrasena

    def run(self) -> None:
        exito, mensaje = ssh_connection.SSHClient(self.conn, contrasena=self.contrasena).test_connection()
        self.terminado.emit(exito, mensaje)
