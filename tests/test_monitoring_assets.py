from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_grafana_dashboard_is_valid_json() -> None:
    dashboard = json.loads(
        (ROOT / "monitoring/grafana/dashboards/photos-sync-observability.json").read_text(
            encoding="utf-8"
        )
    )

    assert dashboard["uid"] == "photos-sync-observability"
    assert {panel["type"] for panel in dashboard["panels"]} >= {"stat", "timeseries", "logs"}


def test_required_monitoring_configuration_exists() -> None:
    required = (
        "monitoring/prometheus/prometheus.yml",
        "monitoring/prometheus/alerts.yml",
        "monitoring/loki/loki.yml",
        "monitoring/loki/rules/fake/alerts.yml",
        "monitoring/alloy/config.alloy",
        "monitoring/grafana/provisioning/datasources/datasources.yml",
        "monitoring/grafana/provisioning/dashboards/dashboards.yml",
    )
    assert all((ROOT / path).is_file() for path in required)
