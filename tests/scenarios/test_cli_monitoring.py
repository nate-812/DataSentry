import json
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

import datasentry.cli.app as cli_app
from datasentry.cli.app import app
from datasentry.monitoring import (
    AlertSmokeReport,
    MonitoringCheckResult,
    MonitoringDeploymentReport,
)

runner = CliRunner()


def test_monitoring_deployment_check_outputs_report(
    monkeypatch,
) -> None:
    def fake_load(path: Path):
        assert path == Path("config/monitoring.example.toml")
        return SimpleNamespace(endpoints=object())

    def fake_run(*, endpoints, client=None):
        del endpoints, client
        return MonitoringDeploymentReport(
            status="passed",
            checks=[
                MonitoringCheckResult(
                    name="prometheus_ready",
                    status="passed",
                    summary="Prometheus readiness 正常",
                )
            ],
        )

    monkeypatch.setattr(cli_app, "load_monitoring_deployment_config", fake_load, raising=False)
    monkeypatch.setattr(cli_app, "run_monitoring_deployment_check", fake_run, raising=False)

    result = runner.invoke(
        app,
        [
            "monitoring",
            "deployment-check",
            "--config-file",
            "config/monitoring.example.toml",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "passed"
    assert payload["checks"][0]["name"] == "prometheus_ready"


def test_monitoring_deployment_check_exits_two_when_report_failed(monkeypatch) -> None:
    def fake_load(path: Path):
        del path
        return SimpleNamespace(endpoints=object())

    def fake_run(*, endpoints, client=None):
        del endpoints, client
        return MonitoringDeploymentReport(
            status="failed",
            checks=[
                MonitoringCheckResult(
                    name="prometheus_rules_loaded",
                    status="failed",
                    summary="Prometheus 缺少关键 StreamLake 告警规则",
                )
            ],
        )

    monkeypatch.setattr(cli_app, "load_monitoring_deployment_config", fake_load, raising=False)
    monkeypatch.setattr(cli_app, "run_monitoring_deployment_check", fake_run, raising=False)

    result = runner.invoke(
        app,
        [
            "monitoring",
            "deployment-check",
            "--config-file",
            "config/monitoring.example.toml",
        ],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"


def test_monitoring_alert_smoke_outputs_report(monkeypatch) -> None:
    def fake_load(path: Path):
        assert path == Path("config/monitoring.example.toml")
        return SimpleNamespace(endpoints=object())

    def fake_smoke(*, endpoints, payload, client=None):
        del endpoints, payload, client
        return AlertSmokeReport(
            status="passed",
            incident_id="incident-1",
            diagnosis_question="为什么 K线数据不更新",
            steps=[],
        )

    monkeypatch.setattr(cli_app, "load_monitoring_deployment_config", fake_load, raising=False)
    monkeypatch.setattr(cli_app, "run_alertmanager_smoke", fake_smoke, raising=False)

    result = runner.invoke(
        app,
        [
            "monitoring",
            "alert-smoke",
            "--config-file",
            "config/monitoring.example.toml",
            "--payload-file",
            "tests/fixtures/alertmanager/kline_freshness_firing.json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "passed"
    assert payload["incident_id"] == "incident-1"
