from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_grafana_dashboards_are_valid_json() -> None:
    dashboard_dir = ROOT / "monitoring/grafana/dashboards"
    dashboards = [json.loads(path.read_text(encoding="utf-8")) for path in dashboard_dir.glob("*.json")]

    assert {dashboard["uid"] for dashboard in dashboards} == {
        "api-rest-observability",
        "hardware-infrastructure",
    }
    panel_types = {panel["type"] for dashboard in dashboards for panel in dashboard["panels"]}
    assert panel_types >= {"row", "stat", "timeseries", "logs", "piechart", "bargauge"}

    dashboard = next(item for item in dashboards if item["uid"] == "api-rest-observability")
    variables = [variable["name"] for variable in dashboard["templating"]["list"]]
    assert variables == ["service", "route", "method", "status_code", "correlation_id"]
    assert sum(panel["type"] == "row" for panel in dashboard["panels"]) == 5
    assert sum(panel["type"] == "stat" for panel in dashboard["panels"]) == 4

    serialized = json.dumps(dashboard)
    assert "http_requests_total" in serialized
    assert "photos_http_requests_total" not in serialized
    assert "correlation_id" in serialized
    assert '"mode": "fixedColor"' not in serialized

    hardware = next(item for item in dashboards if item["uid"] == "hardware-infrastructure")
    hardware_serialized = json.dumps(hardware)
    assert hardware["title"] == "Hardware e Infraestructura"
    assert [variable["name"] for variable in hardware["templating"]["list"]] == ["container"]
    assert sum(panel["type"] == "row" for panel in hardware["panels"]) == 5
    assert "container_cpu_usage_seconds_total" in hardware_serialized
    assert "container_memory_working_set_bytes" in hardware_serialized
    assert "container_network_receive_bytes_total" in hardware_serialized
    assert "container_fs_reads_bytes_total" in hardware_serialized
    assert "pg_up" in hardware_serialized
    assert '"mode": "fixedColor"' not in hardware_serialized


def test_only_the_requested_grafana_alerts_are_active() -> None:
    alerts = (
        ROOT / "monitoring/grafana/provisioning/alerting/api-rest-alerts.yml"
    ).read_text(encoding="utf-8")

    assert alerts.count("      - uid:") == 3
    assert alerts.count("        isPaused: false") == 3
    assert "api-rest-high-5xx-rate" in alerts
    assert "api-rest-no-traffic" in alerts
    assert "api-rest-high-average-latency" in alerts


def test_required_monitoring_configuration_exists() -> None:
    required = (
        "monitoring/prometheus/prometheus.yml",
        "monitoring/prometheus/alerts.yml",
        "monitoring/loki/loki.yml",
        "monitoring/loki/rules/fake/alerts.yml",
        "monitoring/alloy/config.alloy",
        "monitoring/grafana/provisioning/datasources/datasources.yml",
        "monitoring/grafana/provisioning/dashboards/dashboards.yml",
        "monitoring/grafana/provisioning/alerting/api-rest-alerts.yml",
    )
    assert all((ROOT / path).is_file() for path in required)


def test_prometheus_alert_rules_cover_self_hosted_failures() -> None:
    document = yaml.safe_load(
        (ROOT / "monitoring/prometheus/alerts.yml").read_text(encoding="utf-8")
    )
    rules = [rule for group in document["groups"] for rule in group["rules"]]
    names = {rule["alert"] for rule in rules}

    assert len(rules) >= 10
    assert names >= {
        "PhotosSyncApiDown",
        "PhotosSyncPostgresDown",
        "PhotosSyncHighHttp5xxRate",
        "PhotosSyncHighP95Latency",
        "PhotosSyncPipelineFailed",
        "PhotosSyncPipelineStuck",
        "PhotosSyncWebDavJobFailed",
        "PhotosSyncWebDavJobStuck",
        "PhotosSyncContainerMemoryHigh",
        "PhotosSyncFilesystemNearlyFull",
    }
    assert all(rule.get("for") for rule in rules)
    assert all(rule.get("labels", {}).get("severity") in {"warning", "critical"} for rule in rules)
