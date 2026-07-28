# Photos Sync — Backlog

Tickets ordered by priority. PS-1 through PS-3 are already done.

---

## 🔴 High priority

### PS-7 · Add CI pipeline and linter config

**Problem:** `pyproject.toml` declares `mypy` and `pytest` as dev dependencies but there is no `.github/workflows/`, no `ruff` config, and no `mypy` config. Nothing prevents a broken import or a type error from reaching `main` — exactly what happened with the i18n migration (PS-1).

**Solution:**
- Add `.github/workflows/ci.yml` running on every push and pull request:
  - `ruff check photos_sync/ tests/`
  - `mypy photos_sync/`
  - `pytest tests/ -q`
- Add `[tool.ruff]` and `[tool.mypy]` sections to `pyproject.toml`
- Add `ruff` and `mypy` to the `[dev]` optional dependency list

**Files:** `.github/workflows/ci.yml`, `pyproject.toml`

---

### PS-4 · Parallelize SSH server scanning

**Problem:** `export_metadata_json()` in `download.py` scans SSH source servers one by one. The `_net_executor` (ThreadPoolExecutor) already exists in `web_server.py` but is not used for this. With three servers, step 1 takes the sum of all three scan times instead of the max.

**Solution:** Parallelize `scan_ssh_server()` calls using `concurrent.futures.ThreadPoolExecutor` directly inside `download.py` (no dependency on `web_server.py`). Each SFTP connection is independent. Merge results in order after all futures complete. Add a `max_workers` parameter defaulting to `4`.

**Files:** `photos_sync/download.py`

---

### PS-5 · Extract HTML/CSS/JS from `web_server.py` into `static/`

**Problem:** `web_server.py` is 939 lines, ~500 of which are an HTML/CSS/JS string. No syntax highlighting, no browser caching, impossible to lint, painful to edit.

**Solution:**
- Create `photos_sync/static/index.html` with the full Tailwind dashboard
- Serve it with FastAPI's `FileResponse` and mount `StaticFiles` for any assets
- `web_server.py` drops to ~400 lines of pure Python

**Files:** `photos_sync/web_server.py`, `photos_sync/static/index.html`

---

## 🟠 Medium priority

### PS-6 · SSH retry logic and reconnection on transfer failure

**Problem:** In `upload_ssh.py` and `organize.py`, if the SFTP connection drops mid-transfer (e.g. the NAS goes to sleep), the exception aborts the entire run. There are no retries, no reconnection, and no record of which files failed so they can be retried.

**Solution:**
- Wrap `SSHClient.upload()` and `SSHClient.download()` with an exponential backoff retry decorator (3 attempts, 1s / 2s / 4s delays)
- On connection error, attempt to reconnect once before counting as failure
- Collect failed paths into a `list[str]` and print them at the end of the step so the user knows exactly what to re-run
- Add a `--retry-failed` flag to the CLI

**Files:** `photos_sync/ssh_connection.py`, `photos_sync/upload_ssh.py`, `photos_sync/organize.py`, `photos_sync/cli.py`

---

### PS-9 · Centralize date format constant

**Problem:** The string `'%Y-%m-%d %H:%M:%S'` appears in 4 files: `download.py`, `organize.py`, `summary.py`, and the test fixtures in `conftest.py`. Changing the format requires touching all of them.

**Solution:**
- Add `DATE_FORMAT = '%Y-%m-%d %H:%M:%S'` to `config.py`
- Add two helpers to a new `photos_sync/dates.py` module:
  - `parse_date(s: str) -> datetime`
  - `format_date(dt: datetime) -> str`
- Replace all inline `strptime`/`strftime` calls with these helpers

**Files:** `photos_sync/config.py`, `photos_sync/dates.py` *(new)*, `photos_sync/download.py`, `photos_sync/organize.py`, `photos_sync/summary.py`

---

### PS-10 · Dashboard error state separate from empty state

**Problem:** When `GET /api/days` fails (network error, server down), the JS calls `console.error` and leaves the gallery grid showing "Loading…" forever. The user cannot distinguish a network failure from a legitimate empty state ("no photos organized yet").

**Solution:**
- In the dashboard JS, wrap `loadDays()` in a proper try/catch that renders a distinct error card with a "Retry" button
- Add an HTTP status and `error` field to the `/api/days` response schema so the frontend can distinguish server-side errors from empty results
- Empty state shows the camera icon + "Run the Pipeline" call to action
- Error state shows a warning icon + error message + retry button

**Files:** `photos_sync/web_server.py` (HTML/JS section)

---

## 🟢 New features

### PS-11 · Photo thumbnails in gallery day cards

**Problem:** Day cards show a count and size but not what the photos actually look like. There is no way to preview content without opening the filesystem.

**Solution:**
- Add `GET /api/thumbnail/{capture_id}` endpoint that:
  - Reads `capture.dest_path` from `METADATA_JSON`
  - Generates a 200×200 JPEG thumbnail using Pillow (lazy, cached to `~/PhotosSync/thumbnails/`)
  - Returns it as `image/jpeg`
- Update each day card in the dashboard to show a 2×2 mosaic of the first 4 thumbnails
- Add `Pillow` to the optional `[web]` dependency group in `pyproject.toml`

**Files:** `photos_sync/web_server.py`, `pyproject.toml`

---

### PS-12 · Day detail view

**Problem:** Clicking a day card does nothing. There is no way to see the individual photos in a day, download the ZIP, or delete a specific capture from the metadata.

**Solution:**
- Add `GET /api/days/{date}` endpoint returning the full list of `Capture` objects for that day (via `DaySummary.capture_ids` cross-referenced with `METADATA_JSON`)
- Add a slide-in detail panel in the dashboard triggered by clicking a day card, showing:
  - Full-size thumbnail grid (reusing PS-11)
  - ZIP download button (served via `GET /api/days/{date}/zip`)
  - Total size and photo count
  - "Re-organize this day" button (re-runs step 2 filtered to that date)

**Files:** `photos_sync/web_server.py`, `photos_sync/summary.py`

---

### PS-13 · Scheduled pipeline runs

**Problem:** The pipeline only runs when triggered manually via the web UI, the GUI, or the CLI. There is no way to set up nightly automated syncs.

**Solution:**
- Add `APScheduler` to optional dependencies (`pip install photos-sync[scheduler]`)
- Add a `SchedulerManager` class (mirroring `PipelineManager`) that wraps `BackgroundScheduler`
- Expose new endpoints:
  - `GET /api/schedule` — current schedule config
  - `POST /api/schedule` — set cron expression + enabled flag
  - `DELETE /api/schedule` — disable
- Add a "Schedule" tab to the dashboard showing next run time, last run result, and run history (last 10 entries stored in `~/PhotosSync/data/schedule_log.json`)

**Files:** `photos_sync/web_server.py`, `photos_sync/scheduler.py` *(new)*, `pyproject.toml`

---

### PS-14 · Write a proper README

**Problem:** The README is literally one line: `python -m photos_sync.web_server`. No description, no installation instructions, no explanation of the four entry points, no platform notes.

**Solution:** Write a complete README covering:
- What the project does (one paragraph)
- Pipeline diagram showing the 5 steps
- Installation: `pip install -e ".[ssh]"`
- The four ways to run it: web UI, GUI, CLI (`photos-sync --help`), headless (`run_all.py`)
- Platform notes: WebDAV mounting (`net use`) is Windows-only; SSH works everywhere
- Configuration: where `~/PhotosSync/data/` lives, how to change it
- Development: `pip install -e ".[dev]"`, running tests, CI badge

**Files:** `README.md`

---

## Completed ✅

| Ticket | Description |
|--------|-------------|
| PS-1 | Fix broken test suite after i18n migration — 106/106 passing |
| PS-2 | Replace `dict[str, Any]` with typed `Capture` and `DaySummary` dataclasses |
| PS-3 | Encapsulate pipeline globals in `PipelineManager` and `LogBroadcaster` |
| Bug fixes | `ejecutar_todo.py` ImportError, hardcoded `C:\Develop`, JSON files in `cwd`, server on `0.0.0.0`, SSH private key exposed in API |
| i18n | Full English translation: all files, identifiers, comments, docstrings |
| Refactor | Extract `json_io.py` helpers, deduplicate JSON I/O across 7 modules |
| UI | Rebuilt dashboard with Tailwind CSS, sky-blue theme, gallery landing page |
