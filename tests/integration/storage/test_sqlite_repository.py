from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from datasentry.domain import (
    Evidence,
    EvidenceStatus,
    Finding,
    Incident,
    IncidentStatus,
    Inspection,
    InspectionStatus,
    Observation,
    Operation,
    OperationRisk,
    OperationStatus,
    Severity,
    ToolInvocation,
    ToolName,
    ToolStatus,
)
from datasentry.errors import NotFoundError, StorageError
from datasentry.storage.sqlite import SQLiteRepository

NOW = datetime(2026, 6, 25, 12, 0, tzinfo=UTC)


@pytest.fixture
def repository(tmp_path: Path) -> SQLiteRepository:
    with SQLiteRepository(tmp_path / "datasentry.db") as instance:
        yield instance


@pytest.fixture
def inspection() -> Inspection:
    return Inspection(
        id="11111111-1111-4111-8111-111111111111",
        question="M0 inspection",
        scope=["simulation"],
        status=InspectionStatus.COMPLETED,
        summary="Simulation completed",
        started_at=NOW,
        finished_at=NOW,
    )


@pytest.fixture
def running_inspection(inspection: Inspection) -> Inspection:
    return inspection.model_copy(
        update={
            "status": InspectionStatus.RUNNING,
            "summary": None,
            "finished_at": None,
        }
    )


@pytest.fixture
def observation(inspection: Inspection) -> Observation:
    return Observation(
        id="22222222-2222-4222-8222-222222222222",
        inspection_id=inspection.id,
        component="datasentry",
        metric_or_fact="simulation_status",
        value={"status": "ok", "production_access": False},
        source="test",
        target="local",
        observed_at=NOW,
    )


@pytest.fixture
def finding(inspection: Inspection) -> Finding:
    evidence = Evidence(
        claim="Simulation completed",
        status=EvidenceStatus.CONFIRMED,
        source="test",
        target="local",
        observed_at=NOW,
        summary="Repository integration test",
    )
    return Finding(
        id="33333333-3333-4333-8333-333333333333",
        inspection_id=inspection.id,
        severity=Severity.INFO,
        status=EvidenceStatus.CONFIRMED,
        claim="Persistence works",
        evidence=[evidence],
        impact="Local only",
        recommendation="Continue",
        unknowns=["Production connectivity is outside M0"],
        created_at=NOW,
    )


def test_save_and_get_inspection_aggregate(
    repository: SQLiteRepository,
    inspection: Inspection,
    observation: Observation,
    finding: Finding,
) -> None:
    repository.save_inspection(inspection)
    repository.add_observation(observation)
    repository.add_finding(finding)

    aggregate = repository.get_inspection(inspection.id)

    assert aggregate.inspection == inspection
    assert aggregate.observations == [observation]
    assert aggregate.findings == [finding]


def test_start_and_complete_inspection_atomically(
    repository: SQLiteRepository,
    running_inspection: Inspection,
    observation: Observation,
    finding: Finding,
) -> None:
    repository.start_inspection(running_inspection)
    completed = running_inspection.model_copy(
        update={
            "status": InspectionStatus.COMPLETED,
            "summary": finding.claim,
            "finished_at": NOW,
        }
    )

    aggregate = repository.complete_inspection(completed, [observation], [finding])

    assert aggregate.inspection == completed
    assert aggregate.observations == [observation]
    assert aggregate.findings == [finding]


def test_complete_inspection_rolls_back_all_children_on_failure(
    repository: SQLiteRepository,
    running_inspection: Inspection,
    observation: Observation,
    finding: Finding,
) -> None:
    repository.start_inspection(running_inspection)
    completed = running_inspection.model_copy(
        update={
            "status": InspectionStatus.COMPLETED,
            "summary": finding.claim,
            "finished_at": NOW,
        }
    )

    with pytest.raises(StorageError):
        repository.complete_inspection(
            completed,
            [observation, observation],
            [finding],
        )

    aggregate = repository.get_inspection(running_inspection.id)
    assert aggregate.inspection == running_inspection
    assert aggregate.observations == []
    assert aggregate.findings == []


def test_fail_inspection_updates_running_record(
    repository: SQLiteRepository,
    running_inspection: Inspection,
) -> None:
    repository.start_inspection(running_inspection)
    failed = running_inspection.model_copy(
        update={
            "status": InspectionStatus.FAILED,
            "summary": "工具编排失败",
            "finished_at": NOW,
        }
    )

    repository.fail_inspection(failed)

    assert repository.get_inspection(failed.id).inspection == failed


def test_inspection_lifecycle_rejects_invalid_target_status(
    repository: SQLiteRepository,
    inspection: Inspection,
) -> None:
    with pytest.raises(StorageError) as start_error:
        repository.start_inspection(inspection)

    with pytest.raises(StorageError) as complete_error:
        repository.complete_inspection(
            inspection.model_copy(update={"status": InspectionStatus.RUNNING}),
            [],
            [],
        )

    with pytest.raises(StorageError) as fail_error:
        repository.fail_inspection(inspection)

    assert {
        start_error.value.code,
        complete_error.value.code,
        fail_error.value.code,
    } == {"storage.invalid_inspection_transition"}


def test_tool_invocation_round_trip(
    repository: SQLiteRepository,
    running_inspection: Inspection,
) -> None:
    repository.start_inspection(running_inspection)
    invocation = ToolInvocation(
        id="66666666-6666-4666-8666-666666666666",
        inspection_id=running_inspection.id,
        tool_name=ToolName.GET_FLINK_JOBS,
        target="flink",
        parameters={"job": "kline"},
        status=ToolStatus.SUCCEEDED,
        observation_count=2,
        started_at=NOW,
        finished_at=NOW + timedelta(milliseconds=10),
        duration_ms=10,
    )

    repository.save_tool_invocation(invocation)

    assert repository.list_tool_invocations(running_inspection.id) == [invocation]


def test_get_missing_inspection_raises_safe_not_found(
    repository: SQLiteRepository,
) -> None:
    with pytest.raises(NotFoundError) as raised:
        repository.get_inspection("missing")

    assert raised.value.code == "storage.inspection_not_found"
    assert "SELECT" not in raised.value.message


def test_duplicate_id_maps_to_storage_conflict(
    repository: SQLiteRepository,
    inspection: Inspection,
) -> None:
    repository.save_inspection(inspection)

    with pytest.raises(StorageError) as raised:
        repository.save_inspection(inspection)

    assert raised.value.code == "storage.conflict"


def test_missing_inspection_reference_maps_to_storage_constraint(
    repository: SQLiteRepository,
    observation: Observation,
) -> None:
    with pytest.raises(StorageError) as raised:
        repository.add_observation(observation)

    assert raised.value.code == "storage.constraint"
    assert "INSERT" not in raised.value.message


def test_incident_save_update_and_get(repository: SQLiteRepository) -> None:
    incident = Incident(
        id="44444444-4444-4444-8444-444444444444",
        title="Kline delayed",
        symptom="Freshness is behind",
        severity=Severity.WARNING,
        opened_at=NOW,
        updated_at=NOW,
    )
    repository.save_incident(incident)
    updated = incident.model_copy(
        update={
            "status": IncidentStatus.RESOLVED,
            "root_cause": "Simulation",
            "updated_at": NOW + timedelta(minutes=1),
            "resolved_at": NOW + timedelta(minutes=1),
        }
    )

    repository.update_incident(updated)

    assert repository.get_incident(incident.id) == updated


def test_operation_save_update_and_get(repository: SQLiteRepository) -> None:
    operation = Operation(
        id="55555555-5555-4555-8555-555555555555",
        name="refresh_diagnosis",
        version="1",
        parameters={"scope": "local"},
        risk=OperationRisk.L1,
        requester="operator",
        requested_at=NOW,
    )
    repository.save_operation(operation)
    updated = operation.model_copy(
        update={
            "status": OperationStatus.SUCCEEDED,
            "approver": "system",
            "approved_at": NOW,
            "executed_at": NOW,
            "verified_at": NOW,
            "result": {"status": "ok"},
        }
    )

    repository.update_operation(updated)

    assert repository.get_operation(operation.id) == updated


def test_closed_repository_rejects_calls(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "datasentry.db")
    repository.close()

    with pytest.raises(StorageError) as raised:
        repository.get_inspection("missing")

    assert raised.value.code == "storage.closed"
