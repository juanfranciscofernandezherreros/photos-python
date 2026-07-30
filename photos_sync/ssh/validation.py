"""SSH connection types and validation rules."""
from __future__ import annotations

from typing import TypedDict

VALID_ROLES: list[str] = ["origen", "destino", "ambos"]
DEFAULT_SSH_PORT: int = 22


class SSHConnection(TypedDict):
    alias: str
    host: str
    puerto: int
    usuario: str
    ruta_remota: str
    ruta_remota_destino: str
    clave_privada: str
    rol: str


def validate_ambos_role(rol: str, ruta_remota: str, ruta_remota_destino: str) -> None:
    """Raise ValueError if role 'ambos' has invalid destination config."""
    if rol != "ambos":
        return
    if not ruta_remota_destino:
        raise ValueError(
            "With role 'ambos' you must specify a 'remote destination path' "
            "different from the source path, otherwise the pipeline would "
            "re-scan the files it just uploaded as new sources."
        )
    if ruta_remota_destino == ruta_remota.rstrip("/"):
        raise ValueError(
            "The remote destination path cannot be the same as the source path "
            "when the role is 'ambos'. Use a different subfolder, e.g. "
            f"'{ruta_remota.rstrip('/')}_organized'."
        )


def effective_destination_path(conn: SSHConnection) -> str:
    """Remote folder where organized files are uploaded to."""
    return conn.get("ruta_remota_destino") or conn["ruta_remota"]
