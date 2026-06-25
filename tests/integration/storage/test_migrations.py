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

    assert version == 1
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
        } <= tables
        assert connection.execute("SELECT version FROM schema_migrations").fetchall() == [(1,)]


def test_upgrade_is_idempotent(tmp_path: Path) -> None:
    database_path = tmp_path / "datasentry.db"

    assert upgrade_database(database_path) == 1
    assert upgrade_database(database_path) == 1

    with closing(connect(database_path)) as connection:
        assert current_schema_version(connection) == 1
        assert connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 1


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
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always", ResourceWarning)
        upgrade_database(tmp_path / "datasentry.db")
        gc.collect()

    assert [
        warning for warning in recorded if "unclosed database" in str(warning.message).lower()
    ] == []
