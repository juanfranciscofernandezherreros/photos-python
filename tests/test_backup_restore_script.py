from __future__ import annotations

from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts/test_backup_restore.sh"


def test_backup_restore_script_is_isolated_and_fail_fast() -> None:
    content = SCRIPT.read_text(encoding="utf-8")

    assert "set -eu" in content
    assert 'RESTORE_DB="photos_sync_restore_test_$$"' in content
    assert "trap cleanup EXIT INT TERM" in content
    assert "dropdb --if-exists" in content
    assert "--set ON_ERROR_STOP=1" in content


def test_backup_restore_script_exercises_production_format() -> None:
    content = SCRIPT.read_text(encoding="utf-8")

    assert "pg_dump --no-password" in content
    assert "| gzip" in content
    assert "gunzip -c" in content
    assert "photos-sync-backup-ok" in content
