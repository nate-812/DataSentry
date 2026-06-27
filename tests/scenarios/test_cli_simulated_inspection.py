import json
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from datasentry.cli.app import app

runner = CliRunner()


def test_database_upgrade_reports_schema_version(tmp_path: Path) -> None:
    database_path = tmp_path / "datasentry.db"

    result = runner.invoke(
        app,
        ["db", "upgrade", "--database-path", str(database_path)],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "database_path": str(database_path),
        "schema_version": 3,
    }


def test_cli_help_uses_chinese_descriptions() -> None:
    result = runner.invoke(app, ["inspection", "simulate", "--help"])

    assert result.exit_code == 0
    assert "创建模拟巡检" in result.stdout
    assert "记录到模拟巡检中的问题" in result.stdout
    assert "SQLite 数据库路径" in result.stdout
    assert "选项" in result.stdout
    assert "显示帮助信息并退出" in result.stdout
    assert "Show this message and exit" not in result.stdout


def test_simulate_then_show_round_trip(tmp_path: Path) -> None:
    database_path = tmp_path / "datasentry.db"

    simulate = runner.invoke(
        app,
        [
            "inspection",
            "simulate",
            "--database-path",
            str(database_path),
            "--question",
            "M0 simulated inspection",
        ],
    )

    assert simulate.exit_code == 0
    created = json.loads(simulate.stdout)
    assert created["inspection"]["status"] == "completed"
    assert created["observations"][0]["component"] == "datasentry"
    assert created["observations"][0]["value"]["production_access"] is False
    assert created["findings"][0]["status"] == "confirmed"
    assert created["findings"][0]["claim"] == "DataSentry M0 持久化链路运行正常"
    assert created["findings"][0]["evidence"][0]["summary"] == (
        "CLI 已创建本地 SQLite 巡检记录，并从数据库中成功读回"
    )
    assert created["findings"][0]["impact"] == "仅验证本地工程基础，未查询生产系统"
    assert created["findings"][0]["recommendation"] == "M0 评审通过后进入 M1"
    assert created["findings"][0]["unknowns"] == ["生产连接能力不在 M0 范围内"]

    show = runner.invoke(
        app,
        [
            "inspection",
            "show",
            created["inspection"]["id"],
            "--database-path",
            str(database_path),
        ],
    )

    assert show.exit_code == 0
    assert json.loads(show.stdout) == created


def test_show_missing_inspection_returns_safe_json_error(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "inspection",
            "show",
            "missing",
            "--database-path",
            str(tmp_path / "datasentry.db"),
        ],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stderr)
    assert payload["code"] == "storage.inspection_not_found"
    assert payload["message"] == "未找到指定巡检记录"
    assert "traceback" not in result.stderr.lower()
    assert "select " not in result.stderr.lower()


def test_python_module_exposes_same_command_tree() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "datasentry", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "inspection" in result.stdout
    assert "db" in result.stdout
