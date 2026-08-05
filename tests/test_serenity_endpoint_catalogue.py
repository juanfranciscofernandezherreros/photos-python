"""Guard the one-to-one mapping between FastAPI routes and Serenity scenarios."""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
FEATURE = ROOT / "serenity/src/test/resources/features/api_endpoints.feature"
ROW = re.compile(r"^\s*\|\s*(GET|POST|PUT|PATCH|DELETE|WEBSOCKET)\s*\|\s*([^|]+?)\s*\|\s*$")


def _declared_endpoints() -> set[tuple[str, str]]:
    endpoints: set[tuple[str, str]] = set()
    for source in (ROOT / "photos_sync/endpoints").glob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                    continue
                method = decorator.func.attr.upper()
                if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "WEBSOCKET"}:
                    continue
                if decorator.args and isinstance(decorator.args[0], ast.Constant):
                    endpoints.add((method, str(decorator.args[0].value)))
    return endpoints


def _serenity_endpoints() -> set[tuple[str, str]]:
    rows = set()
    for line in FEATURE.read_text(encoding="utf-8").splitlines():
        if match := ROW.match(line):
            rows.add((match.group(1), match.group(2)))
    return rows


def test_serenity_covers_every_endpoint_exactly_once():
    declared = _declared_endpoints()
    covered = _serenity_endpoints()
    assert covered == declared, (
        f"Missing in Serenity: {sorted(declared - covered)}; "
        f"stale in Serenity: {sorted(covered - declared)}"
    )


def test_feature_does_not_duplicate_endpoint_rows():
    matches = [ROW.match(line) for line in FEATURE.read_text(encoding="utf-8").splitlines()]
    rows = [(match.group(1), match.group(2)) for match in matches if match]
    assert len(rows) == len(set(rows))
