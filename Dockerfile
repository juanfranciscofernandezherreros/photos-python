# syntax=docker/dockerfile:1
# ─── Build stage ──────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# System deps needed by psycopg2-binary and Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
# README.md is referenced in pyproject.toml but not needed for the install itself.
# Create a placeholder so pip doesn't error if the file is absent from the context.
RUN echo "# Photos Sync" > README.md
COPY photos_sync/ photos_sync/

# Install the package with ssh + images extras (includes Pillow and paramiko)
RUN pip install --no-cache-dir ".[ssh,images]"

# ─── Runtime stage ────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

ARG APP_UID=10001
ARG APP_GID=10001

# Runtime system libs only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid "$APP_GID" photos-sync \
    && useradd --uid "$APP_UID" --gid "$APP_GID" --create-home --shell /usr/sbin/nologin photos-sync

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/photos-sync* /usr/local/bin/
COPY --from=builder --chown=photos-sync:photos-sync /app /app

# Photos are stored under /data (mount your host folder here)
ENV PHOTOS_DIR=/data \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8765

# Keep Path.home()/PhotosSync mapped to the bind-mounted library while the
# process runs without root privileges.
RUN mkdir -p /data \
    && chown photos-sync:photos-sync /data \
    && ln -s /data /home/photos-sync/PhotosSync \
    && chown -h photos-sync:photos-sync /home/photos-sync/PhotosSync

USER photos-sync:photos-sync

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8765/health')" || exit 1

# Start: wait for DB (handled by depends_on + healthcheck in compose),
# then init tables and launch the web server binding on all interfaces.
CMD ["python", "-m", "photos_sync", "--host", "0.0.0.0", "--port", "8765"]
