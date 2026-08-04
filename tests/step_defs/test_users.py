"""Step definitions for users.feature."""
from __future__ import annotations

import pytest
from pytest_bdd import given, parsers, scenarios, then, when
from starlette.testclient import TestClient

from photos_sync.web_server import app

scenarios("../features/users.feature")


@pytest.fixture()
def ctx(cwd_temporal):
    """Fresh, UNauthenticated client for the users feature (overrides the
    shared ctx which auto-creates an admin)."""
    return {
        "client": TestClient(app),
        "tmp": cwd_temporal,
        "resp": None,
    }


# ── Given ───────────────────────────────────────────────────────────

@given("the API is running", target_fixture="ctx")
def api_running_users(ctx):
    return ctx


@given(parsers.parse('an admin "{username}" exists with password "{password}"'))
def admin_exists(ctx, username, password):
    ctx["resp"] = ctx["client"].post(
        "/api/auth/setup-admin", json={"username": username, "password": password}
    )


@given(parsers.parse('a user "{username}" exists with password "{password}"'))
def user_exists(ctx, username, password):
    ctx["client"].post("/api/users",
                       json={"username": username, "password": password, "role": "user"})


# ── When ────────────────────────────────────────────────────────────

@when(parsers.parse('I setup an admin "{username}" with password "{password}"'))
def setup_admin(ctx, username, password):
    ctx["resp"] = ctx["client"].post(
        "/api/auth/setup-admin", json={"username": username, "password": password}
    )


@when(parsers.parse('I register a user "{username}" with password "{password}" role "{role}"'))
def register_user(ctx, username, password, role):
    ctx["resp"] = ctx["client"].post(
        "/api/users", json={"username": username, "password": password, "role": role}
    )


@when("I log out")
def log_out(ctx):
    ctx["resp"] = ctx["client"].post("/api/auth/logout")


@when(parsers.parse('I log in as "{username}" with password "{password}"'))
def log_in(ctx, username, password):
    ctx["resp"] = ctx["client"].post(
        "/api/auth/login", json={"username": username, "password": password}
    )


# ── Then ────────────────────────────────────────────────────────────

@then(parsers.parse('"{key}" is false'))
def key_is_false(ctx, key):
    assert ctx["resp"].json().get(key) is False


@then(parsers.parse('the created user role is "{role}"'))
def created_role(ctx, role):
    assert ctx["resp"].json()["user"]["role"] == role
