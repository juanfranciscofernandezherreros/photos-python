"""Step definitions for albums.feature."""
from __future__ import annotations
from pathlib import Path
from pytest_bdd import scenarios, when, then, parsers

scenarios("../features/albums.feature")


# ── When ────────────────────────────────────────────────────────────

@when(parsers.parse('I POST "/api/albums" with name "{name}"'))
def create_album(ctx, name):
    ctx["resp"] = ctx["client"].post("/api/albums", json={"name": name})
    if ctx["resp"].status_code == 200:
        album = ctx["resp"].json().get("album", {})
        ctx["albums"][album.get("id")] = album
        ctx["album_ids"].append(album.get("id"))


@when('I PATCH the album with name "New Name"')
def patch_new(ctx):
    ctx["resp"] = ctx["client"].patch(f"/api/albums/{ctx['album_ids'][-1]}", json={"name": "New Name"})


@when('I PATCH the album with name "  "')
def patch_blank(ctx):
    ctx["resp"] = ctx["client"].patch(f"/api/albums/{ctx['album_ids'][-1]}", json={"name": "  "})


@when(parsers.parse('I PATCH "/api/albums/{aid}" with name "{name}"'))
def patch_by_id(ctx, aid, name):
    ctx["resp"] = ctx["client"].patch(f"/api/albums/{aid}", json={"name": name})


@when("I DELETE the album")
def del_album(ctx):
    ctx["resp"] = ctx["client"].delete(f"/api/albums/{ctx['album_ids'][-1]}")


@when(parsers.parse('I DELETE "/api/albums/{aid}"'))
def del_by_id(ctx, aid):
    ctx["resp"] = ctx["client"].delete(f"/api/albums/{aid}")


@when("I add all photos to the album")
def add_all(ctx):
    aid = ctx["album_ids"][-1]
    ctx["resp"] = ctx["client"].post(f"/api/albums/{aid}/photos",
                                     json={"paths": ctx["photos"], "action": "add"})


@when(parsers.parse('I add all photos to album "{label}"'))
def add_named(ctx, label):
    aid = [k for k, v in ctx["albums"].items() if v["name"] == label][0]
    ctx["resp"] = ctx["client"].post(f"/api/albums/{aid}/photos",
                                     json={"paths": ctx["photos"], "action": "add"})


@when("I remove the first photo from the album")
def rm_first(ctx):
    aid = ctx["album_ids"][-1]
    ctx["resp"] = ctx["client"].post(f"/api/albums/{aid}/photos",
                                     json={"paths": [ctx["photos"][0]], "action": "remove"})


@when(parsers.parse('I POST album photos with paths ["{path}"] and action "{action}"'))
def post_literal(ctx, path, action):
    ctx["resp"] = ctx["client"].post(f"/api/albums/{ctx['album_ids'][-1]}/photos",
                                     json={"paths": [path], "action": action})


@when(parsers.parse('I POST album photos with paths [] and action "{action}"'))
def post_empty(ctx, action):
    ctx["resp"] = ctx["client"].post(f"/api/albums/{ctx['album_ids'][-1]}/photos",
                                     json={"paths": [], "action": action})


@when(parsers.parse('I POST "/api/albums/{aid}/photos" with paths [] and action "{action}"'))
def post_by_id(ctx, aid, action):
    ctx["resp"] = ctx["client"].post(f"/api/albums/{aid}/photos",
                                     json={"paths": [], "action": action})


@when("I PATCH the album with cover set to the third photo")
def cover_3(ctx):
    ctx["resp"] = ctx["client"].patch(f"/api/albums/{ctx['album_ids'][-1]}",
                                      json={"cover": ctx["photos"][2]})


@when("I PATCH the album with cover set to the second photo")
def cover_2(ctx):
    ctx["resp"] = ctx["client"].patch(f"/api/albums/{ctx['album_ids'][-1]}",
                                      json={"cover": ctx["photos"][1]})


@when("I request GET the album detail")
def get_detail(ctx):
    ctx["resp"] = ctx["client"].get(f"/api/albums/{ctx['album_ids'][-1]}")


# ── Then ────────────────────────────────────────────────────────────

@then(parsers.parse('"total" equals {v:d}'))
def total_eq(ctx, v):
    assert ctx["resp"].json()["total"] == v


@then('the album id starts with "alb_"')
def id_prefix(ctx):
    assert ctx["resp"].json()["album"]["id"].startswith("alb_")


@then(parsers.parse('the album name is "{name}"'))
def alb_name(ctx, name):
    assert ctx["resp"].json()["album"]["name"] == name


@then(parsers.parse("the album count is {n:d}"))
def alb_count(ctx, n):
    assert ctx["resp"].json()["album"]["count"] == n


@then(parsers.parse("the album photo count is {n:d}"))
def photo_count(ctx, n):
    assert ctx["resp"].json()["count"] == n


@then(parsers.parse('the first album name is "{name}"'))
def first_name(ctx, name):
    assert ctx["resp"].json()["albums"][0]["name"] == name


@then("the two album ids are different")
def unique(ctx):
    assert ctx["album_ids"][-1] != ctx["album_ids"][-2]


@then("the albums list is empty")
def empty(ctx):
    assert ctx["client"].get("/api/albums").json()["total"] == 0


@then(parsers.parse("the album has {n:d} photos"))
def n_photos(ctx, n):
    assert len(ctx["resp"].json()["photos"]) == n


@then('each photo has "id", "filename", "exists", "url"')
def shape(ctx):
    for p in ctx["resp"].json()["photos"]:
        for k in ("id", "filename", "exists", "url"):
            assert k in p


@then("the first album cover is the first photo")
def cover_1st(ctx):
    assert ctx["resp"].json()["albums"][0]["cover"] == ctx["photos"][0]


@then("the first album cover is the third photo")
def cover_3rd(ctx):
    assert ctx["resp"].json()["albums"][0]["cover"] == ctx["photos"][2]


@then("the album cover is not the first photo")
def cover_not_1(ctx):
    aid = ctx["album_ids"][-1]
    a = next(x for x in ctx["client"].get("/api/albums").json()["albums"] if x["id"] == aid)
    assert a["cover"] != ctx["photos"][0]


@then(parsers.parse('album "{label}" has {n:d} photo'))
def named_count(ctx, label, n):
    aid = [k for k, v in ctx["albums"].items() if v["name"] == label][0]
    assert ctx["client"].get(f"/api/albums/{aid}").json()["count"] == n


@then("all original photo files still exist on disk")
def files_ok(ctx):
    for p in ctx["photos"]:
        assert Path(p).is_file()
