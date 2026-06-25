"""Typer command tree for local development and emergency inspection access."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer

from datasentry.config import Settings
from datasentry.domain import (
    Evidence,
    EvidenceStatus,
    Finding,
    Inspection,
    InspectionStatus,
    Observation,
    Severity,
)
from datasentry.domain.common import utc_now
from datasentry.errors import DataSentryError
from datasentry.logging import configure_logging, get_logger
from datasentry.storage import InspectionAggregate, SQLiteRepository, upgrade_database

app = typer.Typer(no_args_is_help=True)
db_app = typer.Typer(no_args_is_help=True)
inspection_app = typer.Typer(no_args_is_help=True)
app.add_typer(db_app, name="db")
app.add_typer(inspection_app, name="inspection")

DatabasePathOption = Annotated[
    Path | None,
    typer.Option(
        "--database-path",
        help="SQLite database path. Defaults to DATASENTRY_DATABASE_PATH.",
    ),
]


def _database_path(value: Path | None) -> Path:
    if value is not None:
        return value
    return Settings().database_path


def _write_json(value: object, *, error: bool = False) -> None:
    typer.echo(
        json.dumps(
            value,
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
        ),
        err=error,
    )


def _aggregate_payload(aggregate: InspectionAggregate) -> dict[str, object]:
    return {
        "inspection": aggregate.inspection.model_dump(mode="json"),
        "observations": [
            observation.model_dump(mode="json") for observation in aggregate.observations
        ],
        "findings": [finding.model_dump(mode="json") for finding in aggregate.findings],
    }


def _run_json(action: Callable[[], object]) -> None:
    try:
        _write_json(action())
    except DataSentryError as error:
        _write_json(error.to_dict(), error=True)
        raise typer.Exit(code=2) from error
    except Exception as error:
        get_logger(__name__).error(
            "cli.unexpected_error",
            error_type=type(error).__name__,
        )
        _write_json(
            {
                "code": "internal.error",
                "details": {},
                "message": "An unexpected error occurred",
            },
            error=True,
        )
        raise typer.Exit(code=1) from error


@db_app.command("upgrade")
def db_upgrade(database_path: DatabasePathOption = None) -> None:
    """Apply pending SQLite migrations."""
    path = _database_path(database_path)
    _run_json(
        lambda: {
            "database_path": str(path),
            "schema_version": upgrade_database(path),
        }
    )


@inspection_app.command("simulate")
def inspection_simulate(
    question: Annotated[
        str,
        typer.Option("--question", help="Question recorded for the simulated inspection."),
    ],
    database_path: DatabasePathOption = None,
) -> None:
    """Create, persist, and read back a local simulated inspection."""
    path = _database_path(database_path)

    def simulate() -> dict[str, object]:
        observed_at = utc_now()
        inspection = Inspection(
            question=question,
            scope=["simulation"],
            status=InspectionStatus.COMPLETED,
            summary="M0 local persistence simulation completed",
            started_at=observed_at,
            finished_at=observed_at,
        )
        observation = Observation(
            inspection_id=inspection.id,
            component="datasentry",
            metric_or_fact="m0_simulation_status",
            value={"status": "ok", "production_access": False},
            source="datasentry_cli",
            target="local",
            observed_at=observed_at,
        )
        evidence = Evidence(
            claim="M0 local simulation completed",
            status=EvidenceStatus.CONFIRMED,
            source="datasentry_cli",
            target="local",
            observed_at=observed_at,
            summary="The CLI created and read back a local SQLite inspection",
        )
        finding = Finding(
            inspection_id=inspection.id,
            severity=Severity.INFO,
            status=EvidenceStatus.CONFIRMED,
            claim="DataSentry M0 persistence path is operational",
            evidence=[evidence],
            impact="Local engineering foundation only; no production system was queried",
            recommendation="Proceed with M1 after M0 review",
            unknowns=["Production connectivity is outside M0 scope"],
            created_at=observed_at,
        )
        with SQLiteRepository(path) as repository:
            repository.save_inspection(inspection)
            repository.add_observation(observation)
            repository.add_finding(finding)
            return _aggregate_payload(repository.get_inspection(inspection.id))

    _run_json(simulate)


@inspection_app.command("show")
def inspection_show(
    inspection_id: Annotated[str, typer.Argument(help="Inspection identifier.")],
    database_path: DatabasePathOption = None,
) -> None:
    """Read a persisted inspection aggregate."""
    path = _database_path(database_path)

    def show() -> dict[str, object]:
        with SQLiteRepository(path) as repository:
            return _aggregate_payload(repository.get_inspection(inspection_id))

    _run_json(show)


def main() -> None:
    """Configure process logging and run the CLI."""
    settings = Settings()
    configure_logging(level=settings.log_level, log_format=settings.log_format)
    app()
