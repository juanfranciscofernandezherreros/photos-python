"""Fail CI unless every Cucumber scenario contains request/response evidence."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parents[1]
FEATURE = ROOT / "serenity/src/test/resources/features/api_endpoints.feature"
REPORT = ROOT / "serenity/target/site/serenity"
ROW = re.compile(r"^\s*\|\s*(GET|POST|PUT|PATCH|DELETE|WEBSOCKET)\s*\|")
FORBIDDEN_VALUES = (
    "Serenity-test-123!",
    "Other-test-123!",
    "BDD-test-123!",
    "New-test-123!",
)


def _expected_counts() -> Counter[str]:
    methods = [match.group(1) for line in FEATURE.read_text(encoding="utf-8").splitlines()
               if (match := ROW.match(line))]
    http = sum(method != "WEBSOCKET" for method in methods)
    websocket = len(methods) - http
    return Counter({
        "HTTP request": http,
        "HTTP response": http,
        "WebSocket request": websocket,
        "WebSocket response": websocket,
    })


def _report_titles(value: object):
    if isinstance(value, dict):
        if isinstance(value.get("title"), str):
            yield value["title"]
        for child in value.values():
            yield from _report_titles(child)
    elif isinstance(value, list):
        for child in value:
            yield from _report_titles(child)


def main() -> None:
    index = REPORT / "index.html"
    if not index.is_file():
        raise SystemExit(f"Missing Serenity HTML report: {index}")

    json_reports = list(REPORT.glob("*.json"))
    if not json_reports:
        raise SystemExit(f"No Serenity JSON results found in {REPORT}")

    actual: Counter[str] = Counter()
    serialized_reports = ""
    for path in json_reports:
        raw = path.read_text(encoding="utf-8")
        serialized_reports += raw
        actual.update(_report_titles(json.loads(raw)))

    expected = _expected_counts()
    evidence = Counter({title: actual[title] for title in expected})
    if evidence != expected:
        raise SystemExit(f"Incomplete request/response evidence: expected {expected}, got {evidence}")

    leaked = [secret for secret in FORBIDDEN_VALUES if secret in serialized_reports]
    if leaked:
        raise SystemExit("Serenity report contains an unredacted test credential")

    print(f"Serenity evidence verified: {dict(evidence)}; no credentials exposed")


if __name__ == "__main__":
    main()
