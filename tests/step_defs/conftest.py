"""Shared BDD fixtures and step definitions reused across all feature files."""
from __future__ import annotations

from pathlib import Path

import pytest
from pytest_bdd import given, when, then, parsers
from starlette.testclient import TestClient
from photos_sync.web_server import app


@pytest.fixture()
def ctx(cwd_temporal):
    """Mutable context dict shared across all steps of a single scenario."""
    client = TestClient(app)
    # Bootstrap + auto-login an admin so protected endpoints work
    client.post("/api/auth/setup-admin",
                json={"username": "admin", "password": "admin12345"})
    return {
        "client": client,
        "tmp": cwd_temporal,
        "photos": [],
        "albums": {},
        "album_ids": [],
        "resp": None,
    }


# ═══════════════════════════════════════════════════════════════════
#  Helper utilities
# ═══════════════════════════════════════════════════════════════════

def make_organized(tmp, day="2024/01/15", n=3, real_jpeg=False, prefix="IMG"):
    folder = tmp / "organizado"
    for part in day.split("/"):
        folder = folder / part
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(n):
        f = folder / f"{prefix}_{i:03}.jpg"
        if real_jpeg:
            from PIL import Image
            Image.new("RGB", (800, 600), (100, 150, 200)).save(f, "JPEG")
        else:
            f.write_bytes(b"fakejpeg" * 20)
        paths.append(str(f))
    return paths


# ═══════════════════════════════════════════════════════════════════
#  Shared GIVEN steps
# ═══════════════════════════════════════════════════════════════════

@given("the API is running", target_fixture="ctx")
def api_running(ctx):
    return ctx


@given("a destination folder exists with organized photos")
def organized_photos(ctx):
    ctx["photos"] = make_organized(ctx["tmp"])


@given("the organized folder is empty")
def organized_empty(ctx):
    import shutil
    folder = ctx["tmp"] / "organizado"
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True, exist_ok=True)
    ctx["photos"] = []


@given("a photo exists at the organized path")
def one_photo(ctx):
    if not ctx["photos"]:
        ctx["photos"] = make_organized(ctx["tmp"], n=1)


@given("a real JPEG photo exists")
def real_jpeg(ctx):
    ctx["photos"] = make_organized(ctx["tmp"], n=1, real_jpeg=True)


@given(parsers.parse("{n:d} photos exist at the organized path"))
def n_photos(ctx, n):
    ctx["photos"] = make_organized(ctx["tmp"], day="2024/05/20", n=n, prefix="PH")


@given(parsers.parse("{n:d} photo exists at the organized path"))
def one_photo_singular(ctx, n):
    ctx["photos"] = make_organized(ctx["tmp"], day="2024/05/20", n=n, prefix="PH")


@given(parsers.parse('an album "{name}" exists'))
def album_exists(ctx, name):
    r = ctx["client"].post("/api/albums", json={"name": name})
    album = r.json()["album"]
    ctx["albums"][album["id"]] = album
    ctx["album_ids"].append(album["id"])


@given("all photos are added to the album")
def all_added(ctx):
    aid = ctx["album_ids"][-1]
    ctx["client"].post(f"/api/albums/{aid}/photos",
                       json={"paths": ctx["photos"], "action": "add"})


@given("only the first photo is added to the album")
def first_added(ctx):
    aid = ctx["album_ids"][-1]
    ctx["client"].post(f"/api/albums/{aid}/photos",
                       json={"paths": [ctx["photos"][0]], "action": "add"})


@given("the cover is set to the first photo")
def cover_first_given(ctx):
    aid = ctx["album_ids"][-1]
    ctx["client"].patch(f"/api/albums/{aid}", json={"cover": ctx["photos"][0]})


@given('an SSH server "backup" exists with role "destino"')
def ssh_backup(ctx):
    ctx["client"].post("/api/ssh", json={
        "alias": "backup", "host": "10.0.0.1", "puerto": 22,
        "usuario": "bk", "ruta_remota": "/bk", "rol": "destino",
    })


# ═══════════════════════════════════════════════════════════════════
#  Shared WHEN steps
# ═══════════════════════════════════════════════════════════════════

@when(parsers.parse('I request GET "{url}"'))
def get_url(ctx, url):
    ctx["resp"] = ctx["client"].get(url)


@when('I request GET "/api/photo" with the photo path')
def get_photo(ctx):
    ctx["resp"] = ctx["client"].get(f"/api/photo?path={ctx['photos'][0]}")


@when('I request GET "/api/thumb" with the photo path and size 200')
def get_thumb(ctx):
    ctx["resp"] = ctx["client"].get(f"/api/thumb?path={ctx['photos'][0]}&size=200")


# ═══════════════════════════════════════════════════════════════════
#  Shared THEN steps
# ═══════════════════════════════════════════════════════════════════

@then(parsers.parse("the response status is {code:d}"))
def check_status(ctx, code):
    assert ctx["resp"].status_code == code, (
        f"Expected {code}, got {ctx['resp'].status_code}: {ctx['resp'].text[:300]}"
    )


@then(parsers.parse('the JSON has key "{key}" with a list'))
def json_key_list(ctx, key):
    assert isinstance(ctx["resp"].json().get(key), list)


@then(parsers.parse('the JSON has key "{key}"'))
def json_key_exists(ctx, key):
    assert key in ctx["resp"].json()


@then(parsers.parse('"{key}" equals {val:d}'))
def json_key_eq_int(ctx, key, val):
    assert ctx["resp"].json()[key] == val


@then(parsers.parse('"{key}" is true'))
def key_true(ctx, key):
    assert ctx["resp"].json().get(key) is True


@then(parsers.parse('"{key}" is an empty list'))
def key_empty_list(ctx, key):
    assert ctx["resp"].json().get(key) == []


@then(parsers.parse('the content type starts with "{prefix}"'))
def ct_prefix(ctx, prefix):
    ct = ctx["resp"].headers.get("content-type", "")
    assert ct.startswith(prefix), f"Expected {prefix}*, got {ct}"


@then(parsers.parse('the content type is "{ct}"'))
def ct_exact(ctx, ct):
    assert ctx["resp"].headers.get("content-type") == ct


@then(parsers.parse('the body contains "{text}"'))
def body_contains(ctx, text):
    assert text in ctx["resp"].text


@then("the response is an empty list")
def resp_empty_list(ctx):
    assert ctx["resp"].json() == []
