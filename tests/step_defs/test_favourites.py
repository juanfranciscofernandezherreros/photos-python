"""Step definitions for favourites.feature."""
from __future__ import annotations

from pathlib import Path

from pytest_bdd import parsers, scenarios, then, when

scenarios("../features/favourites.feature")


@when("I POST \"/api/favourites\" with path and favourite true")
def fav_true(ctx):
    ctx["resp"] = ctx["client"].post("/api/favourites",
                                     json={"path": ctx["photos"][0], "favourite": True})


@when("I POST \"/api/favourites\" with path and favourite false")
def fav_false(ctx):
    ctx["resp"] = ctx["client"].post("/api/favourites",
                                     json={"path": ctx["photos"][0], "favourite": False})


@when(parsers.parse('I POST "/api/photos/bulk" with all paths and action "{action}"'))
def bulk_all(ctx, action):
    ctx["resp"] = ctx["client"].post("/api/photos/bulk",
                                     json={"paths": ctx["photos"], "action": action})


@when(parsers.parse('I POST "/api/photos/bulk" with {n:d} path and action "{action}"'))
def bulk_n(ctx, n, action):
    ctx["resp"] = ctx["client"].post("/api/photos/bulk",
                                     json={"paths": ctx["photos"][:n], "action": action})


@when(parsers.parse('I POST "/api/photos/bulk" with {n:d} paths and action "{action}"'))
def bulk_n2(ctx, n, action):
    ctx["resp"] = ctx["client"].post("/api/photos/bulk",
                                     json={"paths": ctx["photos"][:n], "action": action})


@when(parsers.parse('I POST "/api/photos/bulk" with paths ["{path}"] and action "{action}"'))
def bulk_literal(ctx, path, action):
    ctx["resp"] = ctx["client"].post("/api/photos/bulk",
                                     json={"paths": [path], "action": action})


@then('"favourites" contains the photo path')
def favs_has(ctx):
    assert ctx["photos"][0] in ctx["resp"].json()["favourites"]


@then('"favourites" does not contain the photo path')
def favs_not(ctx):
    assert ctx["photos"][0] not in ctx["resp"].json()["favourites"]


@then("the original files no longer exist")
def gone(ctx):
    for p in ctx["photos"][:2]:
        assert not Path(p).exists()


@then(parsers.parse("a .trash folder contains {n:d} files"))
def trash_n(ctx, n):
    trash = Path(ctx["photos"][0]).parent.parent.parent / ".trash"
    assert trash.exists() and len(list(trash.iterdir())) == n
