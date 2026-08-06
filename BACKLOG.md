# Photos Sync Roadmap

This roadmap tracks remaining engineering work after the CI, security, performance, observability, migration, and recovery milestones.

## High priority

### PS-15: Positive external-service integration flows

Serenity covers every endpoint, while some SSH and WebDAV cases still use controlled failures. Add reproducible fake servers for successful connection, discovery, download, retry, and resume flows.

### PS-16: Alert delivery

Prometheus and Grafana evaluate availability, error-rate, latency, job, and capacity rules. Add an opt-in Alertmanager or equivalent contact point and document notification routing.

### PS-17: Historical schema upgrade fixtures

Alembic adopts existing installations and CI validates a clean PostgreSQL 16 database. Preserve anonymized fixtures for every published schema and test every supported upgrade path.

## Medium priority

### PS-18: Frontend modularization

Split `photos_sync/web/static/index.html` into domain-focused modules and add browser linting and tests without requiring a heavy build chain for self-hosted deployments.

### PS-19: Repository-layer modularization

Split `photos_sync/repository.py` by gallery, album, user, trash, and configuration domains while retaining stable transactions and access APIs.

### PS-20: Optional pipeline scheduling

Provide simple nightly synchronization with execution history without requiring an external scheduler.

## Completed milestones

| Area | Result |
|---|---|
| CI | Ruff, mypy, Python 3.11/3.12, coverage, Serenity, PostgreSQL 16, and build gates. |
| Tests | More than 380 tests, 80% minimum branch coverage, and complete endpoint catalog validation. |
| BDD | Serenity HTML report with sanitized HTTP and WebSocket requests and responses. |
| Database | PostgreSQL, bulk operations, `capture_day`, indexes, and automatic Alembic migrations. |
| Recovery | Daily backups and an isolated destructive dump/restore verification. |
| Security | File-mounted secrets, bcrypt, lockout, rate limiting, and injection-safe command execution. |
| WebDAV | Concurrent transfers, database batches, per-file progress, targeted retry, and HTTP Range resume. |
| SSH | Parallel discovery, retry, and transfer reconnection. |
| Observability | Metrics, structured logs, Prometheus, Grafana, Loki, and actionable alert rules. |
| Runtime | Non-root container with dropped Linux capabilities. |
| Documentation | Deployment, HTTPS, migration, testing, backup, restore, and operations guidance. |
