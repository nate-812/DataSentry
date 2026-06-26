import json
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from datasentry.cli import app as cli_module
from datasentry.cli.app import app
from datasentry.diagnosis import DiagnosisResult
from datasentry.domain import (
    Evidence,
    EvidenceStatus,
    Finding,
    Inspection,
    InspectionStatus,
    Severity,
)
from datasentry.knowledge import QuestionType, RouteMatch
from datasentry.storage import InspectionAggregate
from datasentry.tools import LiveInspectionResult

runner = CliRunner()
NOW = datetime(2026, 6, 25, 12, 0, tzinfo=UTC)


class StubLiveService:
    def run(self, question: str) -> LiveInspectionResult:
        inspection = Inspection(
            id="inspection-1",
            question=question,
            scope=["data_stale"],
            status=InspectionStatus.COMPLETED,
            summary="当前证据不足",
            started_at=NOW,
            finished_at=NOW,
        )
        finding = Finding(
            inspection_id=inspection.id,
            severity=Severity.INFO,
            status=EvidenceStatus.UNKNOWN,
            claim="当前证据不足",
            evidence=[
                Evidence(
                    claim="当前证据不足",
                    status=EvidenceStatus.UNKNOWN,
                    source="test",
                    observed_at=NOW,
                    summary="本地 CLI 场景",
                )
            ],
            impact="仅测试 CLI",
            recommendation="开启云端后执行真实只读探测",
            unknowns=["尚未连接生产"],
            created_at=NOW,
        )
        return LiveInspectionResult(
            diagnosis=DiagnosisResult(
                route=RouteMatch(
                    question_type=QuestionType.DATA_STALE,
                    required_topic_ids=("03", "04"),
                    matched_keywords=("不更新",),
                ),
                knowledge=[],
                lineage_checkpoints=[],
                aggregate=InspectionAggregate(
                    inspection=inspection,
                    observations=[],
                    findings=[finding],
                ),
            ),
            tool_invocations=[],
        )


def test_inspection_run_help_is_chinese() -> None:
    result = runner.invoke(app, ["inspection", "run", "--help"])

    assert result.exit_code == 0
    assert "执行真实只读巡检" in result.stdout
    assert "目标配置 TOML" in result.stdout


def test_inspection_run_outputs_live_result_without_exposing_secrets(
    tmp_path: Path,
    monkeypatch,
) -> None:
    targets = tmp_path / "targets.toml"
    targets.write_text("[hosts]\n", encoding="utf-8")
    monkeypatch.setattr(
        cli_module,
        "build_live_inspection_service",
        lambda **_: StubLiveService(),
    )

    result = runner.invoke(
        app,
        [
            "inspection",
            "run",
            "--question",
            "为什么K线不更新",
            "--targets-file",
            str(targets),
            "--knowledge-root",
            str(Path(__file__).resolve().parents[2] / "knowledge"),
            "--database-path",
            str(tmp_path / "datasentry.db"),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["route"]["question_type"] == "data_stale"
    assert payload["aggregate"]["inspection"]["status"] == "completed"
    assert payload["tool_invocations"] == []
