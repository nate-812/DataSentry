"""Versioned SQLite schema migrations bundled with the package."""

import sqlite3
from importlib import resources
from pathlib import Path

from datasentry.errors import StorageError


def connect(database_path: Path) -> sqlite3.Connection:
    """Create a configured SQLite connection."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def current_schema_version(connection: sqlite3.Connection) -> int:
    """Return the latest applied migration version."""
    row = connection.execute(
        "SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations"
    ).fetchone()
    if row is None:
        return 0
    return int(row["version"])


def upgrade_database(database_path: Path) -> int:
    """Apply all pending bundled migrations and return the current version."""
    connection = connect(database_path)
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        connection.commit()

        applied = current_schema_version(connection)
        migration_root = resources.files("datasentry.storage.sql")
        migrations = sorted(
            (
                resource
                for resource in migration_root.iterdir()
                if resource.name[:4].isdigit() and resource.name.endswith(".sql")
            ),
            key=lambda resource: resource.name,
        )
        for migration in migrations:
            version = int(migration.name[:4])
            if version <= applied:
                continue
            script = migration.read_text(encoding="utf-8")
            transactional_script = (
                "BEGIN IMMEDIATE;\n"
                f"{script}\n"
                "INSERT INTO schema_migrations(version, applied_at) "
                f"VALUES ({version}, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));\n"
                "COMMIT;"
            )
            try:
                connection.executescript(transactional_script)
            except sqlite3.Error as error:
                if connection.in_transaction:
                    connection.rollback()
                raise StorageError(
                    code="storage.migration_failed",
                    message="Database migration failed",
                    details={
                        "database_path": str(database_path),
                        "version": version,
                    },
                ) from error
            applied = version
        return applied
    finally:
        connection.close()
