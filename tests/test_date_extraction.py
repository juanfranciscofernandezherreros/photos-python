"""
Tests for filename → capture_date extraction and the /api/photos/fix-dates
recovery endpoint.

Motivating case: WebDAV downloads saved capture_date = time of download
(all photos on the same day). Filenames like Screenshot_20250629-133659.png
carry the real photo date; we extract it to correct the grouping.
"""
from __future__ import annotations

from photos_sync.utils.dates import extract_date_from_filename

# ── Filename parser ──────────────────────────────────────────────────────

class TestFilenameDateExtraction:
    def test_android_screenshot(self):
        assert extract_date_from_filename(
            "Screenshot_20250629-133659.png"
        ) == "2025-06-29T13:36:59"

    def test_real_user_files(self):
        """The 3 filename shapes actually seen in the user's DB."""
        # 1. Google Pixel style Screenshot_YYYYMMDD-HHMMSS
        assert extract_date_from_filename(
            "Screenshot_20250630-141718.png"
        ) == "2025-06-30T14:17:18"
        # 2. MIUI/Xiaomi Screenshot_YYYY-MM-DD-HH-MM-SS-msms_appname
        assert extract_date_from_filename(
            "Screenshot_2023-11-25-16-43-36-993_com.bbva.bbvacontigo.jpg"
        ) == "2023-11-25T16:43:36"
        # 3. Camera IMG_YYYYMMDD_HHMMSS
        assert extract_date_from_filename(
            "IMG_20230326_223815.jpg"
        ) == "2023-03-26T22:38:15"

    def test_miui_screenshot_without_app_suffix(self):
        assert extract_date_from_filename(
            "Screenshot_2023-11-25-16-43-36.jpg"
        ) == "2023-11-25T16:43:36"

    def test_miui_screenshot_with_ms(self):
        # The 993 (milliseconds) after the seconds must not confuse the parser
        assert extract_date_from_filename(
            "Screenshot_2024-01-15-09-30-05-123_com.whatsapp.jpg"
        ) == "2024-01-15T09:30:05"

    def test_android_screenshot_no_prefix_leak(self):
        # Real files from the user's phone
        assert extract_date_from_filename(
            "Screenshot_20250629-192616.png"
        ) == "2025-06-29T19:26:16"

    def test_camera_photo(self):
        assert extract_date_from_filename(
            "IMG_20240115_101530.jpg"
        ) == "2024-01-15T10:15:30"

    def test_video(self):
        assert extract_date_from_filename(
            "VID_20230801_193045.mp4"
        ) == "2023-08-01T19:30:45"

    def test_iphone_style(self):
        assert extract_date_from_filename(
            "2025-06-29 13.36.59.jpg"
        ) == "2025-06-29T13:36:59"

    def test_date_only(self):
        # Falls back to date-only pattern → time 00:00:00
        assert extract_date_from_filename(
            "Screenshot_20250629.png"
        ) == "2025-06-29T00:00:00"

    def test_no_date_returns_empty(self):
        assert extract_date_from_filename("random_photo.jpg") == ""
        assert extract_date_from_filename("") == ""
        assert extract_date_from_filename("IMG_1234.jpg") == ""

    def test_invalid_date_rejected(self):
        # Month 13 is not valid — must not be accepted
        assert extract_date_from_filename("Screenshot_20251333-000000.png") == ""

    def test_invalid_time_falls_back_to_midnight(self):
        # Bad time part → fall through to date-only pattern
        result = extract_date_from_filename("Screenshot_20250629-994571.png")
        assert result.startswith("2025-06-29")

    def test_year_out_of_range(self):
        # 1899 not accepted (below 1970)
        assert extract_date_from_filename("photo_18991231_120000.jpg") == ""


# ── /api/photos/fix-dates endpoint ────────────────────────────────────────

class TestFixDatesEndpoint:
    def _make(self, cwd, filename, cap_date):
        """Insert a capture into the DB and return its path."""
        from photos_sync import repository as repo
        f = cwd / "incoming" / filename
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"x" * 500)
        repo.upsert_captures([{
            "id":            str(f),
            "archivo":       filename,
            "formato":       f.suffix.lstrip(".").lower(),
            "tamano_mb":     0.001,
            "mtime":         0,
            "fecha_captura": cap_date,
            "ruta_original": str(f),
            "ruta_destino":  str(f),
            "tags":          [],
        }])
        return str(f)

    def test_fixes_screenshot_filename(self, cliente_api, cwd_temporal):
        from photos_sync import repository as repo
        path = self._make(cwd_temporal, "Screenshot_20250629-133659.png",
                          "2026-08-03T15:34:12")   # wrong date passed in
        # upsert_captures auto-corrected it at insert time
        row = repo.get_capture_by_dest(path)
        assert row["fecha_captura"] == "2025-06-29T13:36:59"
        # fix-dates finds nothing to fix
        r = cliente_api.post("/api/photos/fix-dates")
        assert r.status_code == 200
        assert r.json()["skipped_already_good"] == 1

    def test_leaves_correct_dates_alone(self, cliente_api, cwd_temporal):
        # Already-correct date must not be counted as updated
        self._make(cwd_temporal, "IMG_20240115_101530.jpg",
                   "2024-01-15T10:15:30")
        r = cliente_api.post("/api/photos/fix-dates")
        assert r.json()["updated"] == 0
        assert r.json()["skipped_already_good"] == 1

    def test_skips_files_without_date_in_name(self, cliente_api, cwd_temporal):
        self._make(cwd_temporal, "random.jpg", "2026-08-03T15:34:12")
        r = cliente_api.post("/api/photos/fix-dates")
        assert r.json()["updated"] == 0
        assert r.json()["skipped_no_pattern"] == 1

    def test_mixed_batch(self, cliente_api, cwd_temporal):
        # 3 with date patterns — auto-corrected at insert time
        self._make(cwd_temporal, "Screenshot_20250101-090000.png",
                   "2026-08-03T00:00:00")
        self._make(cwd_temporal, "Screenshot_20250102-090000.png",
                   "2026-08-03T00:00:00")
        self._make(cwd_temporal, "Screenshot_20250103-090000.png",
                   "2026-08-03T00:00:00")
        # 1 already matching its pattern
        self._make(cwd_temporal, "IMG_20240115_101530.jpg",
                   "2024-01-15T10:15:30")
        # 1 no pattern at all
        self._make(cwd_temporal, "no-date-here.jpg",
                   "2026-08-03T00:00:00")

        r = cliente_api.post("/api/photos/fix-dates")
        body = r.json()
        assert body["total"] == 5
        # All 4 pattern files are already correct (set at insert time)
        assert body["skipped_already_good"] == 4
        assert body["updated"] == 0
        assert body["skipped_no_pattern"] == 1

    def test_regroups_gallery_by_real_date(self, cliente_api, cwd_temporal):
        """Dates are derived at insert time, so the gallery is grouped
        correctly from the start — no fix-dates needed."""
        self._make(cwd_temporal, "Screenshot_20250629-133659.png",
                   "2026-08-03T15:34:12")
        self._make(cwd_temporal, "Screenshot_20250630-090000.png",
                   "2026-08-03T15:34:13")

        # Already two different real days at insert time
        r = cliente_api.get("/api/days").json()
        assert r["total_photos"] == 2
        assert len(r["days"]) == 2
        dates = {d["fecha"] for d in r["days"]}
        assert "2025-06-29" in dates
        assert "2025-06-30" in dates

    def test_requires_admin(self, cliente_user):
        r = cliente_user.post("/api/photos/fix-dates")
        assert r.status_code == 403
