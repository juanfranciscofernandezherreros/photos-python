"""SSH connection CRUD — persistence only, no transport."""
from __future__ import annotations

from typing import Optional
from ..config import SSH_CONNECTIONS_JSON
from ..json_io import read_json, write_json
from ..ssh.validation import SSHConnection, VALID_ROLES, DEFAULT_SSH_PORT, validate_ambos_role


def load_ssh_connections() -> list[SSHConnection]:
    """All saved SSH connections."""
    datos = read_json(SSH_CONNECTIONS_JSON, default=[])
    return datos if isinstance(datos, list) else []


def save_ssh_connections(conns: list[SSHConnection]) -> None:
    write_json(SSH_CONNECTIONS_JSON, conns)


def add_or_update_ssh_connection(
    alias: str, host: str, puerto: int, usuario: str,
    ruta_remota: str, clave_privada: str = "", rol: str = "origen",
    ruta_remota_destino: str = "",
) -> list[SSHConnection]:
    """Save or update an SSH connection. Raises ValueError on invalid role config."""
    if rol not in VALID_ROLES:
        rol = "origen"
    ruta_remota = ruta_remota.rstrip("/") or ruta_remota
    ruta_remota_destino = ruta_remota_destino.strip().rstrip("/")

    validate_ambos_role(rol, ruta_remota, ruta_remota_destino)

    conns = load_ssh_connections()
    nueva: SSHConnection = {
        "alias": alias, "host": host,
        "puerto": puerto or DEFAULT_SSH_PORT,
        "usuario": usuario, "ruta_remota": ruta_remota,
        "ruta_remota_destino": ruta_remota_destino,
        "clave_privada": clave_privada, "rol": rol,
    }
    conns = [c for c in conns if c["alias"] != alias]
    conns.append(nueva)
    save_ssh_connections(conns)
    return conns


def remove_ssh_connection(alias: str) -> list[SSHConnection]:
    conns = [c for c in load_ssh_connections() if c["alias"] != alias]
    save_ssh_connections(conns)
    return conns


def get_connection(alias: str) -> Optional[SSHConnection]:
    for c in load_ssh_connections():
        if c["alias"] == alias:
            return c
    return None


def connections_by_role(desired_role: str) -> list[SSHConnection]:
    """Connections whose role matches, including those with role 'ambos'."""
    return [
        c for c in load_ssh_connections()
        if c.get("rol") == desired_role or c.get("rol") == "ambos"
    ]
