from __future__ import annotations

import shutil
import os
from datetime import datetime
from ..utils.dates import parse_date, DATE_FORMAT
from pathlib import Path

from rich.progress import track

from ..storage.folders import load_saved_destination
from ..config import ORGANIZED_DIR
from .. import repository as repo
from ..models import Capture
from .. import ssh_connection


def organize_captures_by_date() -> None:
    """Copy each capture from the database to dest/YYYY/MM/DD based on
    its capture_date, fix the file's filesystem timestamp, and write back the
    dest_path into the metadata so compress.py and summary.py can use it."""
    print(f"Reading captures from database...\n")

    raw = repo.load_captures()
    if raw is None:
        print(f"❌ No captures in database. Run step 1 (download) first.")
        return
    if not isinstance(raw, list):
        print(f"❌ Database error. Run step 1 (download) again.")
        return
    if not raw:
        print("❌ No captures in the metadata file to organize.")
        return

    captures = [Capture.from_dict(d) for d in raw]

    dest_str = load_saved_destination()
    dest_base = Path(dest_str) if dest_str else ORGANIZED_DIR
    print(f"Destination: {dest_base.resolve()}\n")

    copied = 0
    already_existed = 0
    errors = 0

    # SSH clients opened lazily (one per alias, reused for all captures from
    # that server) and closed in the finally block whether or not things succeed.
    ssh_clients: dict[str, ssh_connection.SSHClient] = {}

    def _client_for(alias: str) -> ssh_connection.SSHClient:
        if alias not in ssh_clients:
            saved = ssh_connection.get_connection(alias)
            if saved is None:
                raise RuntimeError(f"SSH connection '{alias}' is no longer saved")
            client = ssh_connection.SSHClient(saved)
            client.connect()
            ssh_clients[alias] = client
        return ssh_clients[alias]

    try:
        for cap in track(captures, description="Organizing by date..."):
            try:
                date = parse_date(cap.capture_date)
                day_folder = dest_base / date.strftime('%Y/%m/%d')
                day_folder.mkdir(parents=True, exist_ok=True)

                dest_file = day_folder / cap.filename

                if dest_file.exists():
                    already_existed += 1
                else:
                    if cap.ssh_alias:
                        _client_for(cap.ssh_alias).download(cap.ssh_remote_path, dest_file)
                    else:
                        shutil.copy2(cap.source_path, dest_file)
                    ts = date.timestamp()
                    os.utime(dest_file, (ts, ts))
                    copied += 1

                cap.dest_path = str(dest_file)

            except (OSError, ValueError, RuntimeError) as e:
                print(f"⚠️ Could not organize '{cap.filename}': {e}")
                errors += 1
    finally:
        for client in ssh_clients.values():
            client.close()

    repo.upsert_captures([c.to_dict() for c in captures])

    print("-" * 50)
    print("ORGANIZE SUMMARY:")
    print(f"  - New copies: {copied}")
    print(f"  - Already existed: {already_existed}")
    if errors:
        print(f"  - Errors: {errors}")
    print(f"\n📁 Organized files are in: {dest_base.resolve()}")


if __name__ == "__main__":
    organize_captures_by_date()
