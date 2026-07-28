"""SSH/SFTP client — transport layer only."""
import stat
from pathlib import Path, PurePosixPath
from typing import Any, Optional

from .validation import SSHConnection, DEFAULT_SSH_PORT

try:
    import paramiko
except ImportError:
    paramiko = None


def paramiko_available() -> bool:
    return paramiko is not None


def _require_paramiko() -> None:
    if paramiko is None:
        raise RuntimeError(
            "Missing library 'paramiko', required for SSH connections. "
            "Install it with: pip install paramiko"
        )


class SSHClient:
    """Wraps an open SSH/SFTP connection to a Linux server."""

    def __init__(self, conn: SSHConnection, password: str = "") -> None:
        _require_paramiko()
        self.conexion = conn  # kept as 'conexion' for backward compat
        self._password = password
        self._ssh: Any = None
        self._sftp: Any = None

    def __enter__(self) -> "SSHClient":
        self.connect()
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    def connect(self) -> None:
        self._ssh = paramiko.SSHClient()
        self._ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kwargs: dict[str, Any] = dict(
            hostname=self.conexion["host"],
            port=int(self.conexion.get("puerto") or DEFAULT_SSH_PORT),
            username=self.conexion["usuario"],
            timeout=15,
        )
        key = self.conexion.get("clave_privada")
        if key:
            kwargs["key_filename"] = str(Path(key).expanduser())
        elif self._password:
            kwargs["password"] = self._password
        else:
            kwargs["allow_agent"] = True
            kwargs["look_for_keys"] = True
        self._ssh.connect(**kwargs)
        self._sftp = self._ssh.open_sftp()

    def close(self) -> None:
        try:
            if self._sftp is not None:
                self._sftp.close()
        finally:
            if self._ssh is not None:
                self._ssh.close()

    def test_connection(self) -> tuple[bool, str]:
        label = f"{self.conexion['usuario']}@{self.conexion['host']}:{self.conexion.get('puerto', 22)}"
        try:
            self.connect()
            path = self.conexion["ruta_remota"]
            self._sftp.listdir(path)
            return True, f"Connection successful to {label} — '{path}' is accessible."
        except Exception as e:
            return False, f"Could not connect to {label} or read '{self.conexion['ruta_remota']}': {e}"
        finally:
            self.close()

    def list_files_recursive(self, remote_path: str, valid_extensions: list[str]) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        try:
            entries = self._sftp.listdir_attr(remote_path)
        except FileNotFoundError:
            return found
        for entry in entries:
            full_path = str(PurePosixPath(remote_path) / entry.filename)
            if stat.S_ISDIR(entry.st_mode):
                found.extend(self.list_files_recursive(full_path, valid_extensions))
            elif PurePosixPath(full_path).suffix.lower() in valid_extensions:
                found.append({"ruta": full_path, "tamano": entry.st_size, "mtime": entry.st_mtime})
        return found

    def download(self, remote_path: str, local_path: Path) -> None:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        self._sftp.get(remote_path, str(local_path))

    def upload(self, local_path: Path, remote_path: str) -> None:
        self._create_remote_directories(str(PurePosixPath(remote_path).parent))
        self._sftp.put(str(local_path), remote_path)

    def remote_exists(self, remote_path: str) -> Optional[int]:
        try:
            return self._sftp.stat(remote_path).st_size
        except FileNotFoundError:
            return None

    def _create_remote_directories(self, remote_path: str) -> None:
        parts = [p for p in PurePosixPath(remote_path).parts if p != "/"]
        current = ""
        for part in parts:
            current += f"/{part}"
            try:
                self._sftp.stat(current)
            except FileNotFoundError:
                self._sftp.mkdir(current)
