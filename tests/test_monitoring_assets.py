from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_grafana_dashboards_are_valid_json() -> None:
    dashboard_dir = ROOT / "monitoring/grafana/dashboards"
    dashboards = [json.loads(path.read_text(encoding="utf-8")) for path in dashboard_dir.glob("*.json")]

    assert {dashboard["uid"] for dashboard in dashboards} == {
        "photos-sync-admin",
        "photos-sync-observability",
    }
    panel_types = {panel["type"] for dashboard in dashboards for panel in dashboard["panels"]}
    assert panel_types >= {"stat", "timeseries", "logs", "table", "bargauge"}


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
