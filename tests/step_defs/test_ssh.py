"""Step definitions for ssh.feature."""
from __future__ import annotations

from pytest_bdd import parsers, scenarios, then, when

scenarios("../features/ssh.feature")


@when(parsers.parse(
    'I POST "/api/ssh" with alias "{alias}" host "{host}" port {port:d} user "{user}" source "{src}" role "{role}"'
))
def post_ssh(ctx, alias, host, port, user, src, role):
    ctx["resp"] = ctx["client"].post("/api/ssh", json={
        "alias": alias, "host": host, "puerto": port,
        "usuario": user, "ruta_remota": src, "rol": role,
    })


@when(parsers.parse('I DELETE "/api/ssh/{alias}"'))
def del_ssh(ctx, alias):
    ctx["resp"] = ctx["client"].delete(f"/api/ssh/{alias}")


@then(parsers.parse('the response contains {n:d} connection with alias "{alias}"'))
def has_conn(ctx, n, alias):
    assert len([c for c in ctx["resp"].json() if c["alias"] == alias]) == n


@then(parsers.parse("there is exactly {n:d} connection"))
def exactly_n(ctx, n):
    assert len(ctx["resp"].json()) == n


@then(parsers.parse('its host is "{host}"'))
def host_is(ctx, host):
    assert ctx["resp"].json()[0]["host"] == host
