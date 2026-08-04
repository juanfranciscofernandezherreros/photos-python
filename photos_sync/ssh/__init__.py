"""SSH package — client, validation, and type definitions."""
from __future__ import annotations

from .client import SSHClient as SSHClient
from .client import paramiko_available as paramiko_available
from .validation import DEFAULT_SSH_PORT as DEFAULT_SSH_PORT
from .validation import VALID_ROLES as VALID_ROLES
from .validation import SSHConnection as SSHConnection
from .validation import effective_destination_path as effective_destination_path
from .validation import validate_ambos_role as validate_ambos_role
