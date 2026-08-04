"""Backward-compatible facade — re-exports from ssh/ and storage/ssh_repo."""
from __future__ import annotations

from .ssh.client import SSHClient as SSHClient  # noqa: F401
from .ssh.client import _require_paramiko as _require_paramiko  # noqa: F401
from .ssh.client import paramiko_available as paramiko_available  # noqa: F401
from .ssh.validation import DEFAULT_SSH_PORT as DEFAULT_SSH_PORT  # noqa: F401
from .ssh.validation import VALID_ROLES as VALID_ROLES  # noqa: F401
from .ssh.validation import SSHConnection as SSHConnection  # noqa: F401
from .ssh.validation import (
    effective_destination_path as effective_destination_path,  # noqa: F401
)
from .ssh.validation import validate_ambos_role as validate_ambos_role  # noqa: F401
from .storage.ssh_repo import (
    add_or_update_ssh_connection as add_or_update_ssh_connection,  # noqa: F401
)
from .storage.ssh_repo import connections_by_role as connections_by_role  # noqa: F401
from .storage.ssh_repo import get_connection as get_connection  # noqa: F401
from .storage.ssh_repo import (
    load_ssh_connections as load_ssh_connections,  # noqa: F401
)
from .storage.ssh_repo import (
    remove_ssh_connection as remove_ssh_connection,  # noqa: F401
)
from .storage.ssh_repo import (
    save_ssh_connections as save_ssh_connections,  # noqa: F401
)
