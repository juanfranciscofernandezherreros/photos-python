"""Backward-compatible facade — re-exports from ssh/ and storage/ssh_repo."""
from .ssh.client import SSHClient, paramiko_available, _require_paramiko
from .ssh.validation import (
    SSHConnection, VALID_ROLES, DEFAULT_SSH_PORT,
    effective_destination_path, validate_ambos_role,
)
from .storage.ssh_repo import (
    load_ssh_connections, save_ssh_connections,
    add_or_update_ssh_connection, remove_ssh_connection,
    get_connection, connections_by_role,
)
