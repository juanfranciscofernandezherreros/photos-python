"""Step definitions for gallery.feature."""
from __future__ import annotations
from pathlib import Path
from pytest_bdd import scenarios, then

scenarios("../features/gallery.feature")


@then('each photo has "id", "filename", "favourite", "url"')
def photo_shape(ctx):
    for p in ctx["resp"].json().get("photos", []):
        for k in ("id", "filename", "favourite", "url"):
            assert k in p, f"Missing {k}"


@then("the response body is smaller than the original file")
def body_smaller(ctx):
    assert len(ctx["resp"].content) < Path(ctx["photos"][0]).stat().st_size


@then("exactly 1 file exists in the thumbs directory")
def one_thumb(ctx):
    assert len(list((ctx["tmp"] / "thumbs").glob("*.jpg"))) == 1
