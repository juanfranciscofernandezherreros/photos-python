"""SSH package — client, validation, and type definitions."""
from .client import SSHClient, paramiko_available
from .validation import SSHConnection, VALID_ROLES, DEFAULT_SSH_PORT, effective_destination_path, validate_ambos_role
