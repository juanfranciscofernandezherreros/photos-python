#!/bin/sh
# Destructive only to an isolated database whose name is generated below.
set -eu

PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-photos}"
PGDATABASE_ADMIN="${PGDATABASE_ADMIN:-postgres}"
RESTORE_DB="photos_sync_restore_test_$$"
WORK_DIR="$(mktemp -d)"
BACKUP_FILE="$WORK_DIR/restore-test.sql.gz"

if [ -z "${PGPASSWORD:-}" ] && [ -f /run/secrets/postgres_password ]; then
  PGPASSWORD="$(tr -d '\r\n' < /run/secrets/postgres_password)"
fi
export PGHOST PGPORT PGUSER PGPASSWORD

cleanup() {
  psql --no-password --dbname "$PGDATABASE_ADMIN" --set ON_ERROR_STOP=1 \
    --command "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$RESTORE_DB' AND pid <> pg_backend_pid();" \
    >/dev/null 2>&1 || true
  dropdb --if-exists --no-password --maintenance-db "$PGDATABASE_ADMIN" "$RESTORE_DB" \
    >/dev/null 2>&1 || true
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT INT TERM

createdb --no-password --maintenance-db "$PGDATABASE_ADMIN" "$RESTORE_DB"
psql --no-password --dbname "$RESTORE_DB" --set ON_ERROR_STOP=1 <<'SQL'
CREATE TABLE backup_restore_probe (
  id integer PRIMARY KEY,
  marker text NOT NULL
);
INSERT INTO backup_restore_probe (id, marker) VALUES (1, 'photos-sync-backup-ok');
SQL

pg_dump --no-password --dbname "$RESTORE_DB" | gzip > "$BACKUP_FILE"
test -s "$BACKUP_FILE"

dropdb --no-password --maintenance-db "$PGDATABASE_ADMIN" "$RESTORE_DB"
createdb --no-password --maintenance-db "$PGDATABASE_ADMIN" "$RESTORE_DB"
gunzip -c "$BACKUP_FILE" | psql --no-password --dbname "$RESTORE_DB" --set ON_ERROR_STOP=1 >/dev/null

RESTORED_MARKER="$(psql --no-password --dbname "$RESTORE_DB" --tuples-only --no-align \
  --set ON_ERROR_STOP=1 --command "SELECT marker FROM backup_restore_probe WHERE id = 1")"
test "$RESTORED_MARKER" = "photos-sync-backup-ok"

echo "Backup restore test passed for isolated database $RESTORE_DB"
