"""SSH connection CRUD — delegates to repository (PostgreSQL)."""
from __future__ import annotations
from typing import Optional
from .. import repository as repo
from ..ssh.validation import SSHConnection


def load_ssh_connections() -> list[SSHConnection]:
    return repo.load_ssh_connections()


def save_ssh_connections(conns: list[SSHConnection]) -> None:
    repo.save_ssh_connections(conns)


def add_or_update_ssh_connection(
    alias: str, host: str, puerto: int, usuario: str,
    ruta_remota: str, clave_privada: str = "", rol: str = "origen",
    ruta_remota_destino: str = "",
) -> list[SSHConnection]:
    return repo.add_or_update_ssh(
        alias=alias, host=host, puerto=puerto, usuario=usuario,
        ruta_remota=ruta_remota, clave_privada=clave_privada,
        rol=rol, ruta_remota_destino=ruta_remota_destino,
    )


def remove_ssh_connection(alias: str) -> list[SSHConnection]:
    return repo.remove_ssh(alias)


def get_connection(alias: str) -> Optional[SSHConnection]:
    return repo.get_ssh(alias)


def connections_by_role(desired_role: str) -> list[SSHConnection]:
    return repo.ssh_by_role(desired_role)
