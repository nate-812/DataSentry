import json
from pathlib import Path

import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[3]

EXPECTED_DASHBOARDS = {
    "datasentry-self-monitoring.json": ("datasentry-self-monitoring", "DataSentry 自监控"),
    "streamlake-doris-freshness.json": (
        "streamlake-doris-freshness",
        "StreamLake Doris 与新鲜度",
    ),
    "streamlake-flink.json": ("streamlake-flink", "StreamLake Flink"),
    "streamlake-hosts.json": ("streamlake-hosts", "StreamLake 主机"),
    "streamlake-kafka.json": ("streamlake-kafka", "StreamLake Kafka"),
    "streamlake-overview.json": ("streamlake-overview", "StreamLake 总览"),
}


def test_prometheus_and_alertmanager_yaml_are_valid() -> None:
    paths = [
        ROOT / "monitoring/prometheus/prometheus.example.yml",
        ROOT / "monitoring/prometheus/rules/streamlake.rules.yml",
        ROOT / "monitoring/alertmanager/alertmanager.example.yml",
        ROOT / "monitoring/grafana/provisioning/datasources/prometheus.yml",
        ROOT / "monitoring/grafana/provisioning/dashboards/streamlake.yml",
    ]

    for path in paths:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict), path


def test_alertmanager_routes_to_datasentry_and_wecom_placeholders() -> None:
    path = ROOT / "monitoring/alertmanager/alertmanager.example.yml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))

    receiver_names = {receiver["name"] for receiver in data["receivers"]}
    assert "datasentry-webhook" in receiver_names
    assert "wecom-robot-placeholder" in receiver_names
    assert "<WECHAT_WORK_BOT_KEY>" in path.read_text(encoding="utf-8")


def test_alertmanager_routes_critical_alerts_to_datasentry_and_wecom() -> None:
    data = yaml.safe_load(
        (ROOT / "monitoring/alertmanager/alertmanager.example.yml").read_text(
            encoding="utf-8"
        )
    )
    routes = data["route"]["routes"]

    datasentry_route = next(
        route for route in routes if route["receiver"] == "datasentry-webhook"
    )
    assert datasentry_route["matchers"] == ['severity =~ "warning|critical"']
    assert datasentry_route["continue"] is True

    wecom_route = next(
        route for route in routes if route["receiver"] == "wecom-robot-placeholder"
    )
    assert wecom_route["matchers"] == ['severity = "critical"']


def test_prometheus_example_scrapes_streamlake_api_jobs() -> None:
    data = yaml.safe_load(
        (ROOT / "monitoring/prometheus/prometheus.example.yml").read_text(
            encoding="utf-8"
        )
    )

    scrape_configs = {
        scrape_config["job_name"]: scrape_config for scrape_config in data["scrape_configs"]
    }
    assert scrape_configs["spring_api"]["static_configs"][0]["targets"] == [
        "data1:8080"
    ]
    assert scrape_configs["spring_api"]["static_configs"][0]["labels"]["service"] == (
        "streamlake"
    )
    assert scrape_configs["ai_engine"]["static_configs"][0]["targets"] == ["data1:8000"]
    assert scrape_configs["ai_engine"]["static_configs"][0]["labels"]["service"] == (
        "streamlake"
    )


def test_prometheus_rules_have_required_groups_and_alert_labels() -> None:
    data = yaml.safe_load(
        (ROOT / "monitoring/prometheus/rules/streamlake.rules.yml").read_text(
            encoding="utf-8"
        )
    )

    groups = data["groups"]
    assert {group["name"] for group in groups} == {
        "datasentry_self",
        "streamlake_api",
        "streamlake_doris",
        "streamlake_flink",
        "streamlake_host",
        "streamlake_kafka",
    }
    for group in groups:
        for rule in group["rules"]:
            labels = rule["labels"]
            assert labels["severity"]
            assert labels["component"]
            assert labels["service"] == "streamlake"


def test_grafana_dashboards_have_uid_title_and_panels() -> None:
    dashboard_dir = ROOT / "monitoring/grafana/dashboards"
    dashboards = sorted(dashboard_dir.glob("*.json"))

    assert {path.name for path in dashboards} == set(EXPECTED_DASHBOARDS)
    for path in dashboards:
        dashboard = json.loads(path.read_text(encoding="utf-8"))
        expected_uid, expected_title = EXPECTED_DASHBOARDS[path.name]
        assert dashboard["uid"] == expected_uid
        assert dashboard["title"] == expected_title
        assert dashboard["schemaVersion"] == 39
        assert dashboard["refresh"] == "30s"
        assert dashboard["tags"] == ["streamlake", "datasentry"]
        assert isinstance(dashboard["panels"], list)
        assert len(dashboard["panels"]) >= 2
