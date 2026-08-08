# Architecture

Photos Sync is a self-hosted FastAPI application backed by PostgreSQL and a host-mounted photo library.

## Main components

- **Web application:** authentication, gallery, configuration, WebDAV ingestion, pipeline control, and metrics.
- **Storage layer:** SQLAlchemy repositories, Alembic migrations, indexed capture dates, normalized per-photo EXIF records, and batched writes.
- **Ingestion:** concurrent WebDAV and SSH discovery and transfer, followed by EXIF extraction, classification, and organization.
- **Observability:** structured application logs in Loki, Prometheus metrics, and provisioned Grafana dashboards and alerts.
- **Recovery:** scheduled compressed database dumps and an isolated restore verification.

The application container runs as a non-root user. PostgreSQL, Grafana, Prometheus, and pgAdmin bind to loopback by default and should remain on private Docker networks in production.

## Compatibility boundary

Some API paths, request fields, internal model attributes, and SSH role values were originally published in Spanish. They are retained as stable external contracts. New documentation, comments, messages, and future versioned APIs use English.
