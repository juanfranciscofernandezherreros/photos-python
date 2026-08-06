# Operations

## Health and diagnostics

```bash
docker compose ps
curl --fail http://localhost:8765/health
docker compose logs app --tail=100
```

An authenticated administrator can inspect `/api/diag` for table counts and database status.

## Monitoring

```bash
docker compose --profile monitoring up -d
```

Grafana is available on port 3000 and includes API and infrastructure dashboards. Prometheus retains metrics for 15 days and Loki retains logs for 14 days by default. Application access logs omit bodies, cookies, authorization headers, and query parameters.

## Backup and restore verification

The backup container writes `photos_sync_YYYYMMDD_HHMMSS.sql.gz` files every 24 hours and removes files older than `BACKUP_KEEP_DAYS`.

```bash
docker compose logs backup --tail=50
docker compose cp scripts/test_backup_restore.sh db:/tmp/test_backup_restore.sh
docker compose exec -T db sh /tmp/test_backup_restore.sh
```

The verification creates, dumps, removes, restores, and validates a temporary database. It never modifies the production `photos_sync` database.

## Incident checklist

1. Stop ingestion jobs that are repeatedly failing.
2. Preserve application and reverse-proxy logs.
3. Check free disk space, PostgreSQL health, and photo-library permissions.
4. Retry failed WebDAV files; partial transfers resume automatically when supported.
5. Test the latest backup before any destructive database recovery.
