"""Tests for downloading photos grouped by capture day."""
from __future__ import annotations

import io
import zipfile


def archive_names(content: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        return sorted(archive.namelist())


def test_downloads_one_day_in_a_named_folder(cliente_api, carpeta_organizada) -> None:
    response = cliente_api.get("/api/days/download-zip?dates=2023-10-24")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "photos_2023-10-24.zip" in response.headers["content-disposition"]
    assert archive_names(response.content) == [
        "2023-10-24/Screenshot_20231024_153020.png"
    ]


def test_downloads_multiple_days_in_separate_folders(cliente_api, carpeta_organizada) -> None:
    response = cliente_api.get(
        "/api/days/download-zip?dates=2023-10-24,2023-10-25"
    )

    assert response.status_code == 200
    assert archive_names(response.content) == [
        "2023-10-24/Screenshot_20231024_153020.png",
        "2023-10-25/Screenshot_20231025_090000.jpg",
    ]


def test_all_downloads_every_available_day(cliente_api, carpeta_organizada) -> None:
    response = cliente_api.get("/api/days/download-zip?dates=all")

    assert response.status_code == 200
    assert "photo_days_2.zip" in response.headers["content-disposition"]
    assert len(archive_names(response.content)) == 2


def test_rejects_invalid_date(cliente_api) -> None:
    response = cliente_api.get("/api/days/download-zip?dates=24-10-2023")

    assert response.status_code == 400
    assert response.json()["detail"] == "Dates must use the YYYY-MM-DD format"


def test_rejects_impossible_calendar_date(cliente_api) -> None:
    response = cliente_api.get("/api/days/download-zip?dates=2023-99-99")

    assert response.status_code == 400
    assert response.json()["detail"] == "Dates must be valid calendar days"


def test_unknown_day_has_no_download(cliente_api, carpeta_organizada) -> None:
    response = cliente_api.get("/api/days/download-zip?dates=1999-01-01")

    assert response.status_code == 404


def test_download_requires_authentication(cliente_anon) -> None:
    cliente_anon.post(
        "/api/auth/setup-admin",
        json={"username": "root", "password": "rootpass1"},
    )
    cliente_anon.post("/api/auth/logout")

    response = cliente_anon.get("/api/days/download-zip?dates=all")

    assert response.status_code == 401
