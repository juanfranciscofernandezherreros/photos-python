# Changelog

All notable changes are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses semantic versioning.

## [Unreleased]

### Added

- Resumable WebDAV transfers with stable partial files and HTTP Range requests.
- Professional GitHub community health files and English documentation policy.

### Changed

- WebDAV discovery removes overlapping roots and defaults to eight transfer workers.
- WebDAV streaming chunks are configurable through `WEBDAV_CHUNK_SIZE_KB`.

### Security

- Application containers run without root privileges and with dropped capabilities.
- Secrets are generated as platform-independent files and excluded from version control.

## [0.1.0] - 2026-08-06

### Added

- Self-hosted WebDAV and SSH photo ingestion.
- FastAPI gallery, PostgreSQL storage, Alembic migrations, backups, monitoring, and endpoint contract tests.
