"""Persistence interfaces and implementations."""

from datasentry.storage.migrations import connect, current_schema_version, upgrade_database
from datasentry.storage.repository import InspectionAggregate, Repository
from datasentry.storage.sqlite import SQLiteRepository

__all__ = [
    "InspectionAggregate",
    "Repository",
    "SQLiteRepository",
    "connect",
    "current_schema_version",
    "upgrade_database",
]
