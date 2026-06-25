import json
from pathlib import Path

from typer.testing import CliRunner

from datasentry.cli.app import app

runner = CliRunner()
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPOSITORY_ROOT / "tests/fixtures/diagnosis"


def _diagnose_args(
    database_path: Path,
    observations_file: Path,
    *,
    question: str = "为什么K线不更新",
    knowledge_root: Path | None = None,
) -> list[str]:
    return [
        "inspection",
        "diagnose",
        "--question",
        question,
        "--observations-file",
        str(observations_file),
        "--knowledge-root",
        str(knowledge_root or REPOSITORY_ROOT / "knowledge"),
        "--database-path",
        str(database_path),
    ]


def test_diagnose_kline_fixture_and_show_round_trip(tmp_path: Path) -> None:
    database_path = tmp_path / "datasentry.db"

    result = runner.invoke(
        app,
        _diagnose_args(database_path, FIXTURES / "kline_job_missing.json"),
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["route"]["question_type"] == "data_stale"
    assert [item["topic_id"] for item in payload["knowledge"]] == ["03", "04"]
    assert [item["node_id"] for item in payload["lineage_checkpoints"]] == [
        "collector",
        "kafka.binance.trade.raw",
        "flink.kline",
        "doris.kline_1min",
        "api.kline.latest",
    ]
    aggregate = payload["aggregate"]
    assert aggregate["findings"][0]["claim"] == "K线链路停在 Flink 计算层"
    assert aggregate["findings"][0]["status"] == "inferred"
    assert len(aggregate["observations"]) == 3

    show = runner.invoke(
        app,
        [
            "inspection",
            "show",
            aggregate["inspection"]["id"],
            "--database-path",
            str(database_path),
        ],
    )

    assert show.exit_code == 0
    assert json.loads(show.stdout) == aggregate


def test_diagnose_insufficient_evidence_returns_unknown(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        _diagnose_args(
            tmp_path / "datasentry.db",
            FIXTURES / "insufficient_evidence.json",
        ),
    )

    assert result.exit_code == 0
    finding = json.loads(result.stdout)["aggregate"]["findings"][0]
    assert finding["status"] == "unknown"
    assert finding["unknowns"] == [
        "Kline Job 当前状态未知",
        "Doris kline_1min 数据新鲜度未知",
    ]


def test_diagnose_rejects_invalid_observation_json(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.json"
    database_path = tmp_path / "datasentry.db"
    invalid.write_text('{"token": "secret"}', encoding="utf-8")

    result = runner.invoke(
        app,
        _diagnose_args(database_path, invalid),
    )

    assert result.exit_code == 2
    payload = json.loads(result.stderr)
    assert payload["code"] == "diagnosis.invalid_observations"
    assert "secret" not in result.stderr
    assert not database_path.exists()


def test_diagnose_rejects_missing_knowledge_root(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        _diagnose_args(
            tmp_path / "datasentry.db",
            FIXTURES / "kline_job_missing.json",
            knowledge_root=tmp_path / "missing",
        ),
    )

    assert result.exit_code == 2
    assert json.loads(result.stderr)["code"] == "knowledge.index_missing"


def test_diagnose_help_is_chinese() -> None:
    result = runner.invoke(app, ["inspection", "diagnose", "--help"])

    assert result.exit_code == 0
    assert "本地模拟 Observation JSON 文件" in result.stdout
    assert "知识库根目录" in result.stdout
