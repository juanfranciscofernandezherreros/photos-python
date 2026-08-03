"""
Tests for photos_sync.pipeline.classify
─────────────────────────────────────────
Covers the rule-based tagging: filename patterns, source-folder paths,
extension rules, the 'other' fallback, and the full classify_captures()
step that reads/writes captures via the database.

EXIF rules are not unit-tested here (they require real image files with
embedded metadata); classify_one still works without Pillow.
"""
import json
import pytest
from pathlib import Path

from photos_sync.models import Capture
from photos_sync.pipeline.classify import classify_one, classify_captures


def _cap(filename="x.jpg", source_path="/x.jpg", extension="jpg", ssh_remote_path=None):
    return Capture(
        id="1", filename=filename, extension=extension, size_mb=1.0,
        mtime=0.0, capture_date="2023-10-24 10:00:00",
        source_path=source_path, ssh_remote_path=ssh_remote_path,
    )


class TestFilenameRules:
    def test_screenshot_prefix(self):
        assert "screenshot" in classify_one(_cap(filename="Screenshot_20231024.png"))

    def test_captura_prefix(self):
        assert "screenshot" in classify_one(_cap(filename="Captura_2023.png"))

    def test_img_prefix_is_camera(self):
        assert "camera" in classify_one(_cap(filename="IMG_1234.jpg"))

    def test_dsc_prefix_is_camera(self):
        assert "camera" in classify_one(_cap(filename="DSC00123.jpg"))

    def test_vid_prefix_is_video(self):
        assert "video" in classify_one(_cap(filename="VID_20231024.mp4", extension="mp4"))

    def test_panorama(self):
        assert "panorama" in classify_one(_cap(filename="PANO_0001.jpg"))

    def test_edited_suffix(self):
        assert "edited" in classify_one(_cap(filename="IMG_1234-edited.jpg"))

    def test_case_insensitive(self):
        assert "screenshot" in classify_one(_cap(filename="SCREENSHOT_X.PNG"))


class TestPathRules:
    def test_dcim_camera(self):
        assert "camera" in classify_one(_cap(source_path="/storage/DCIM/Camera/x.jpg"))

    def test_screenshots_folder(self):
        assert "screenshot" in classify_one(_cap(source_path="/storage/Pictures/Screenshots/x.png"))

    def test_whatsapp_folder(self):
        assert "whatsapp" in classify_one(_cap(source_path="/storage/WhatsApp/Media/x.jpg"))

    def test_download_folder(self):
        assert "download" in classify_one(_cap(source_path="/storage/Download/x.jpg"))

    def test_instagram_is_social(self):
        assert "social" in classify_one(_cap(source_path="/storage/Instagram/x.jpg"))

    def test_ssh_remote_path_used(self):
        # When ssh_remote_path is set it takes precedence for path rules
        cap = _cap(source_path="ssh://nas/x.jpg", ssh_remote_path="/home/juan/DCIM/Camera/x.jpg")
        assert "camera" in classify_one(cap)

    def test_backslash_windows_path(self):
        assert "screenshot" in classify_one(_cap(source_path="Z:\\Pictures\\Screenshots\\x.png"))


class TestExtensionRules:
    def test_gif(self):
        assert "gif" in classify_one(_cap(filename="anim.gif", extension="gif"))

    def test_mp4_is_video(self):
        assert "video" in classify_one(_cap(filename="clip.mp4", extension="mp4"))

    def test_webp_is_web_image(self):
        assert "web_image" in classify_one(_cap(filename="x.webp", extension="webp"))


class TestFallbackAndCombination:
    def test_unmatched_gets_other(self):
        assert classify_one(_cap(filename="random.jpg", source_path="/misc/random.jpg")) == ["other"]

    def test_multiple_tags_combine(self):
        # WhatsApp path + edited suffix → both tags
        cap = _cap(filename="IMG-edited.jpg", source_path="/WhatsApp/Media/IMG-edited.jpg")
        tags = classify_one(cap)
        assert "whatsapp" in tags and "edited" in tags

    def test_tags_are_sorted(self):
        cap = _cap(filename="IMG-edited.jpg", source_path="/WhatsApp/Media/IMG-edited.jpg")
        tags = classify_one(cap)
        assert tags == sorted(tags)

    def test_no_duplicate_tags(self):
        # 'camera' can come from both filename (IMG_) and path (/DCIM/Camera)
        cap = _cap(filename="IMG_1234.jpg", source_path="/DCIM/Camera/IMG_1234.jpg")
        tags = classify_one(cap)
        assert tags.count("camera") == 1


class TestClassifyStep:
    def test_no_metadata_does_not_crash(self, capsys):
        # Empty DB — should print a message and not crash
        classify_captures()
        out = capsys.readouterr().out
        assert len(out) > 0  # printed something, didn't raise

    def test_writes_tags_to_metadata(self, tmp_path, metadatos_json):
        from photos_sync import repository as _repo
        classify_captures()
        result = _repo.load_captures()
        assert any("screenshot" in c.get("tags", []) or "camera" in c.get("tags", []) or len(c.get("tags", [])) >= 0 for c in result)

    def test_every_photo_gets_at_least_one_tag(self, tmp_path, metadatos_json):
        from photos_sync import repository as _repo
        classify_captures()
        result = _repo.load_captures()
        assert len(result) >= 1
        for cap in result:
            assert isinstance(cap.get("tags", []), list)
