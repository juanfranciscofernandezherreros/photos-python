# WebDAV Tuning and Recovery

## Transfer model

The downloader performs one recursive discovery per independent remote root, then transfers files through a bounded worker pool. Completed metadata is persisted in batches. Each in-progress file uses a stable `.webdav.part` path and is promoted atomically after its expected size is validated.

After a disconnect, the next attempt sends `Range: bytes=<partial-size>-`. A compliant server returns `206 Partial Content`, avoiding retransmission. If it returns `200`, Photos Sync safely restarts that file. Existing complete destination files are skipped.

## Tuning

- Start with `WEBDAV_DOWNLOAD_WORKERS=8` on modern Wi-Fi.
- Reduce it to `4` if the phone becomes hot, requests time out, or throughput drops.
- Try `12` or `16` only when the WebDAV server and storage remain responsive.
- Keep `WEBDAV_CHUNK_SIZE_KB=1024` for normal photos; `2048` can help very large videos at the cost of more memory per worker.
- Increase `WEBDAV_DB_BATCH_SIZE` only when database commits are visible in profiling.

Measure total bytes per second over several minutes. A larger worker count is useful only when aggregate throughput improves.

## Recovery

Use **Retry failed** in the WebDAV view after restoring connectivity. The status list identifies the current or failed file, its attempt count, transferred bytes, and whether it resumed from a partial download. Do not manually rename `.webdav.part` files; they are recovery state and are replaced atomically after validation.
