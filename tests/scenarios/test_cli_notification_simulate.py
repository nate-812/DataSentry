import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from datasentry.cli import app as cli_module
from datasentry.cli.app import app
from datasentry.notifications import AlertmanagerPayload, NotificationResult
from datasentry.notifications.messages import NotificationContent

runner = CliRunner()
FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "alertmanager"


class StubNotificationService:
    def build(self, payload: AlertmanagerPayload) -> NotificationResult:
        del payload
        content = NotificationContent(
            status="firing",
            severity="critical",
            component="doris",
            deduplication_key="alertname=KlineFreshnessStale|component=doris",
            diagnosis_question="为什么 K线数据不更新",
            findings=[],
            unknowns=["本地 CLI 替身"],
        )
        return NotificationResult(
            content=content,
            wecom_markdown={
                "msgtype": "markdown",
                "markdown": {"content": "K线数据不更新"},
            },
            generic_webhook={
                "status": "firing",
                "severity": "critical",
                "component": "doris",
                "deduplication_key": "alertname=KlineFreshnessStale|component=doris",
                "diagnosis_question": "为什么 K线数据不更新",
                "diagnosis_status": "unknown",
                "finding_summaries": [],
                "confirmed_evidence": [],
                "unknowns": ["本地 CLI 替身"],
                "recommended_actions": [],
            },
        )


def test_notification_simulate_outputs_wecom_message(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        cli_module,
        "_build_notification_service",
        lambda **_: StubNotificationService(),
    )

    result = runner.invoke(
        app,
        [
            "notification",
            "simulate",
            "--payload-file",
            str(FIXTURE_DIR / "kline_freshness_firing.json"),
            "--format",
            "wecom",
            "--database-path",
            str(tmp_path / "datasentry.db"),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["msgtype"] == "markdown"
    assert "K线数据不更新" in payload["markdown"]["content"]


def test_notification_simulate_outputs_generic_message(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        cli_module,
        "_build_notification_service",
        lambda **_: StubNotificationService(),
    )

    result = runner.invoke(
        app,
        [
            "notification",
            "simulate",
            "--payload-file",
            str(FIXTURE_DIR / "kline_freshness_firing.json"),
            "--format",
            "generic",
            "--database-path",
            str(tmp_path / "datasentry.db"),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["diagnosis_question"] == "为什么 K线数据不更新"
    assert payload["deduplication_key"] == "alertname=KlineFreshnessStale|component=doris"


def test_notification_simulate_closes_repository(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    class FakeRepository:
        def __init__(self, database_path: Path) -> None:
            self.database_path = database_path
            self.is_open = False

        def __enter__(self) -> "FakeRepository":
            self.is_open = True
            calls.append("enter")
            return self

        def __exit__(
            self,
            exc_type: object,
            exc_value: object,
            traceback: object,
        ) -> None:
            self.is_open = False
            calls.append("exit")

    class StubRunner:
        def __init__(self, repository: FakeRepository) -> None:
            self.repository = repository

        def run(self, question: str) -> object:
            del question
            assert self.repository.is_open
            calls.append("run")
            raise RuntimeError("stub diagnosis unavailable")

    def build_stub_runner(**kwargs: object) -> StubRunner:
        repository = kwargs["repository"]
        assert isinstance(repository, FakeRepository)
        return StubRunner(repository)

    monkeypatch.setattr(cli_module, "SQLiteRepository", FakeRepository)
    monkeypatch.setattr("datasentry.cli.app.TargetCatalog.load", lambda _: object())
    monkeypatch.setattr(cli_module, "build_live_inspection_service", build_stub_runner)

    result = runner.invoke(
        app,
        [
            "notification",
            "simulate",
            "--payload-file",
            str(FIXTURE_DIR / "kline_freshness_firing.json"),
            "--format",
            "generic",
            "--database-path",
            str(tmp_path / "datasentry.db"),
        ],
    )

    assert result.exit_code == 0
    assert calls == ["enter", "run", "exit"]
