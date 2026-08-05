"""Generate local Docker secret files without printing their values."""
from __future__ import annotations

import argparse
import secrets
from pathlib import Path

SECRET_FILES = {
    "postgres_password.txt": 32,
    "app_secret_key.txt": 48,
    "grafana_admin_password.txt": 32,
    "pgadmin_password.txt": 32,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", default="secrets")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    directory = Path(args.directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    for filename, byte_count in SECRET_FILES.items():
        path = directory / filename
        if path.exists() and not args.force:
            # Docker Linux containers must not receive a trailing Windows CR
            # as part of passwords consumed directly by command-line tools.
            value = path.read_bytes().rstrip(b"\r\n")
            if not value:
                raise RuntimeError(f"{path} is empty; regenerate it with --force")
            path.write_bytes(value + b"\n")
            print(f"kept {path}")
        else:
            value = secrets.token_urlsafe(byte_count)
            path.write_bytes((value + "\n").encode("utf-8"))
            print(f"generated {path}")
        try:
            path.chmod(0o600)
        except OSError:
            pass


if __name__ == "__main__":
    main()
