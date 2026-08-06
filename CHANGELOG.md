# Changelog

All notable changes are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses semantic versioning.

## [Unreleased]

### Added

- Resumable WebDAV transfers with stable partial files and HTTP Range requests.
- Native WebDAV throughput, queue, worker, resume, and failure metrics for Grafana.
- An option to exclude MP4 videos from WebDAV synchronization.
- Professional GitHub community health files and English documentation policy.

### Changed

- WebDAV discovery removes overlapping roots and the stress profile uses 32 transfer workers.
- WebDAV streaming uses configurable 2 MiB chunks and batched database writes.
- Complete local files are removed from the HTTP worker queue before incremental synchronization.

### Security

- Application containers run without root privileges and with dropped capabilities.
- Secrets are generated as platform-independent files and excluded from version control.

## [0.1.0] - 2026-08-06

### Added

- Self-hosted WebDAV and SSH photo ingestion.
- FastAPI gallery, PostgreSQL storage, Alembic migrations, backups, monitoring, and endpoint contract tests.
