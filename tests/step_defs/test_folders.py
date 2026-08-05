"""Step definitions for folders.feature."""
from __future__ import annotations

from pathlib import Path

from pytest_bdd import parsers, scenarios, then, when

scenarios("../features/folders.feature")


@when(parsers.parse('I POST "/api/carpetas/origen/anadir" with carpeta "{carpeta}"'))
def add_src(ctx, carpeta):
    ctx["resp"] = ctx["client"].post("/api/carpetas/origen/anadir", json={"carpeta": carpeta})


@when(parsers.parse('I POST "/api/carpetas/origen/quitar" with carpeta "{carpeta}"'))
def rm_src(ctx, carpeta):
    ctx["resp"] = ctx["client"].post("/api/carpetas/origen/quitar", json={"carpeta": carpeta})


@when(parsers.parse('I POST "/api/carpetas/destino" with tipo "{tipo}" and ruta "{ruta}"'))
def dest_local(ctx, tipo, ruta):
    ctx["resp"] = ctx["client"].post("/api/carpetas/destino", json={"tipo": tipo, "ruta": ruta})


@when(parsers.parse('I POST "/api/carpetas/destino" with tipo "{tipo}" and alias "{alias}"'))
def dest_ssh(ctx, tipo, alias):
    ctx["resp"] = ctx["client"].post("/api/carpetas/destino", json={"tipo": tipo, "alias": alias})


@when('I POST "/api/carpetas/destino/quitar"')
def rm_dest(ctx):
    ctx["resp"] = ctx["client"].post("/api/carpetas/destino/quitar")


@then(parsers.parse('"origen" contains "{val}"'))
def origen_has(ctx, val):
    assert str(Path(val)) in ctx["resp"].json()["origen"]


@then('the response is a list of steps with "id" and "nombre"')
def steps_shape(ctx):
    data = ctx["resp"].json()
    assert isinstance(data, list) and all("id" in s and "nombre" in s for s in data)
