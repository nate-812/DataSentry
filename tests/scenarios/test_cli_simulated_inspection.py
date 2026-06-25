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
        "schema_version": 1,
    }


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
