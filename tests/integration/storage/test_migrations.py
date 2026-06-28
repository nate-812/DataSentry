import gc
import sqlite3
import warnings
from contextlib import closing
from pathlib import Path

import pytest

from datasentry.storage.migrations import connect, current_schema_version, upgrade_database


def test_upgrade_creates_schema_and_records_version(tmp_path: Path) -> None:
    database_path = tmp_path / "nested" / "datasentry.db"

    version = upgrade_database(database_path)

    assert version == 5
    with closing(sqlite3.connect(database_path)) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert {
            "schema_migrations",
            "inspections",
            "observations",
            "findings",
            "incidents",
            "operations",
            "tool_invocations",
            "runbooks",
            "operation_events",
            "operation_locks",
        } <= tables
        assert connection.execute("SELECT version FROM schema_migrations").fetchall() == [
            (1,),
            (2,),
            (3,),
            (4,),
            (5,),
        ]


def test_upgrade_is_idempotent(tmp_path: Path) -> None:
    database_path = tmp_path / "datasentry.db"

    assert upgrade_database(database_path) == 5
    assert upgrade_database(database_path) == 5

    with closing(connect(database_path)) as connection:
        assert current_schema_version(connection) == 5
        assert connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 5


def test_tool_invocations_schema_contains_audit_fields(tmp_path: Path) -> None:
    database_path = tmp_path / "datasentry.db"
    upgrade_database(database_path)

    with closing(connect(database_path)) as connection:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(tool_invocations)").fetchall()
        }

    assert {
        "inspection_id",
        "tool_name",
        "target",
        "parameters_json",
        "status",
        "observation_count",
        "error_code",
        "error_message",
        "started_at",
        "finished_at",
        "duration_ms",
    } <= columns


def test_upgrade_database_applies_m4_chat_console_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "datasentry.db"

    version = upgrade_database(database_path)

    assert version >= 3
    with closing(connect(database_path)) as connection:
        names = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert {"chat_sessions", "chat_messages", "chat_runs", "chat_run_events"} <= names


def test_migration_0004_creates_incident_memory_tables(tmp_path: Path) -> None:
    database_path = tmp_path / "datasentry.db"

    version = upgrade_database(database_path)

    assert version >= 4
    with closing(connect(database_path)) as connection:
        names = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert "incident_links" in names
    assert "incident_timeline_events" in names
    assert "incident_fingerprints" in names
    assert "incident_rca_reports" in names


def test_migration_0005_adds_operation_idempotency_key(tmp_path) -> None:
    database_path = tmp_path / "datasentry.db"

    upgrade_database(database_path)

    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(operations)").fetchall()
        }
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    assert "idempotency_key" in columns
    assert {"runbooks", "operation_events", "operation_locks"} <= tables


def test_chat_runs_reject_invalid_error_state_combinations(tmp_path: Path) -> None:
    database_path = tmp_path / "datasentry.db"
    upgrade_database(database_path)

    with closing(connect(database_path)) as connection:
        connection.execute(
            """
            INSERT INTO chat_sessions (id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                "22222222-2222-4222-8222-222222222222",
                "K线诊断",
                "2026-06-27T08:00:00+00:00",
                "2026-06-27T08:00:00+00:00",
            ),
        )
        connection.execute(
            """
            INSERT INTO chat_messages (id, session_id, role, content, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "11111111-1111-4111-8111-111111111111",
                "22222222-2222-4222-8222-222222222222",
                "user",
                "为什么K线不更新",
                "2026-06-27T08:00:00+00:00",
            ),
        )

        invalid_runs = [
            (
                "33333333-3333-4333-8333-333333333333",
                "completed",
                "chat.failed",
                "聊天任务失败",
            ),
            (
                "44444444-4444-4444-8444-444444444444",
                "failed",
                " ",
                " ",
            ),
        ]
        for run_id, status, error_code, error_message in invalid_runs:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO chat_runs (
                        id, session_id, user_message_id, status,
                        error_code, error_message, created_at, finished_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        "22222222-2222-4222-8222-222222222222",
                        "11111111-1111-4111-8111-111111111111",
                        status,
                        error_code,
                        error_message,
                        "2026-06-27T08:00:00+00:00",
                        "2026-06-27T08:00:00+00:00",
                    ),
                )


def test_foreign_keys_are_enforced(tmp_path: Path) -> None:
    database_path = tmp_path / "datasentry.db"
    upgrade_database(database_path)

    with (
        closing(connect(database_path)) as connection,
        pytest.raises(sqlite3.IntegrityError),
    ):
        connection.execute(
            """
            INSERT INTO observations (
                id, inspection_id, component, metric_or_fact,
                value_json, source, target, observed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "22222222-2222-4222-8222-222222222222",
                "missing",
                "simulation",
                "status",
                '"ok"',
                "cli",
                None,
                "2026-06-25T12:00:00+00:00",
            ),
        )


def test_upgrade_does_not_leak_sqlite_connections(tmp_path: Path) -> None:
    gc.collect()
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always", ResourceWarning)
        upgrade_database(tmp_path / "datasentry.db")
        gc.collect()

    assert [
        warning for warning in recorded if "unclosed database" in str(warning.message).lower()
    ] == []
