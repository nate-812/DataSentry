import inspect
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from datasentry.chat import (
    ChatEventType,
    ChatMessage,
    ChatRole,
    ChatRun,
    ChatRunStatus,
    ChatSession,
)
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


def test_list_inspections_returns_recent_aggregates_with_limit(
    repository: SQLiteRepository,
    inspection: Inspection,
    observation: Observation,
    finding: Finding,
) -> None:
    older = inspection.model_copy(
        update={
            "id": "12121212-1212-4121-8121-121212121212",
            "started_at": NOW - timedelta(minutes=5),
            "finished_at": NOW - timedelta(minutes=4),
        }
    )
    recent_observation = observation.model_copy(update={"inspection_id": inspection.id})
    recent_finding = finding.model_copy(update={"inspection_id": inspection.id})

    repository.save_inspection(older)
    repository.save_inspection(inspection)
    repository.add_observation(recent_observation)
    repository.add_finding(recent_finding)

    assert repository.list_inspections(limit=1) == [
        repository.get_inspection(inspection.id),
    ]


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


def test_chat_session_message_run_and_event_round_trip(repository: SQLiteRepository) -> None:
    session = ChatSession(
        id="77777777-7777-4777-8777-777777777777",
        title="Kline diagnosis",
        created_at=NOW,
        updated_at=NOW,
    )
    message = ChatMessage(
        id="88888888-8888-4888-8888-888888888888",
        session_id=session.id,
        role=ChatRole.USER,
        content="为什么K线不更新",
        created_at=NOW,
    )
    run = ChatRun(
        id="99999999-9999-4999-8999-999999999999",
        session_id=session.id,
        user_message_id=message.id,
        status=ChatRunStatus.RUNNING,
        created_at=NOW,
    )
    event = ChatRun.Event(
        id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        run_id=run.id,
        event_type=ChatEventType.ACCEPTED,
        payload={"question": "为什么K线不更新"},
        created_at=NOW,
    )

    repository.save_chat_session(session)
    repository.save_chat_message(message)
    repository.save_chat_run(run)
    repository.save_chat_run_event(event)

    assert repository.get_chat_session(session.id) == session
    assert repository.list_chat_sessions(limit=10) == [session]
    assert repository.list_chat_messages(session.id) == [message]
    assert repository.get_chat_run(run.id) == run
    assert repository.list_chat_run_events(run.id) == [event]


def test_update_chat_run_persists_completed_status(repository: SQLiteRepository) -> None:
    session = ChatSession(
        id="71717171-7171-4717-8717-717171717171",
        title="Kline diagnosis",
        created_at=NOW,
        updated_at=NOW,
    )
    message = ChatMessage(
        id="81818181-8181-4818-8818-818181818181",
        session_id=session.id,
        role=ChatRole.USER,
        content="检查K线延迟",
        created_at=NOW,
    )
    run = ChatRun(
        id="91919191-9191-4919-8919-919191919191",
        session_id=session.id,
        user_message_id=message.id,
        status=ChatRunStatus.RUNNING,
        created_at=NOW,
    )
    completed = run.model_copy(
        update={
            "status": ChatRunStatus.COMPLETED,
            "finished_at": NOW + timedelta(seconds=1),
        }
    )

    repository.save_chat_session(session)
    repository.save_chat_message(message)
    repository.save_chat_run(run)
    repository.update_chat_run(completed)

    assert repository.get_chat_run(run.id) == completed


def test_update_chat_run_keeps_identity_fields(repository: SQLiteRepository) -> None:
    session = ChatSession(
        id="72727272-7272-4727-8727-727272727272",
        title="Kline diagnosis",
        created_at=NOW,
        updated_at=NOW,
    )
    message = ChatMessage(
        id="82828282-8282-4828-8828-828282828282",
        session_id=session.id,
        role=ChatRole.USER,
        content="检查K线延迟",
        created_at=NOW,
    )
    run = ChatRun(
        id="92929292-9292-4929-8929-929292929292",
        session_id=session.id,
        user_message_id=message.id,
        status=ChatRunStatus.RUNNING,
        created_at=NOW,
    )
    reassigned = ChatRun(
        id=run.id,
        session_id="changed-session",
        user_message_id="changed-message",
        status=ChatRunStatus.COMPLETED,
        created_at=NOW + timedelta(minutes=1),
        finished_at=NOW + timedelta(minutes=2),
    )

    repository.save_chat_session(session)
    repository.save_chat_message(message)
    repository.save_chat_run(run)
    repository.update_chat_run(reassigned)

    updated = repository.get_chat_run(run.id)
    assert updated.session_id == run.session_id
    assert updated.user_message_id == run.user_message_id
    assert updated.created_at == run.created_at
    assert updated.status is ChatRunStatus.COMPLETED
    assert updated.finished_at == reassigned.finished_at


def test_chat_message_and_event_lists_are_limited(repository: SQLiteRepository) -> None:
    session = ChatSession(
        id="73737373-7373-4737-8737-737373737373",
        title="Kline diagnosis",
        created_at=NOW,
        updated_at=NOW,
    )
    first_message = ChatMessage(
        id="83838383-8383-4838-8838-838383838383",
        session_id=session.id,
        role=ChatRole.USER,
        content="第一条消息",
        created_at=NOW,
    )
    second_message = ChatMessage(
        id="84848484-8484-4848-8848-848484848484",
        session_id=session.id,
        role=ChatRole.ASSISTANT,
        content="第二条消息",
        created_at=NOW + timedelta(seconds=1),
    )
    run = ChatRun(
        id="93939393-9393-4939-8939-939393939393",
        session_id=session.id,
        user_message_id=first_message.id,
        status=ChatRunStatus.RUNNING,
        created_at=NOW,
    )
    first_event = ChatRun.Event(
        id="a1aaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        run_id=run.id,
        event_type=ChatEventType.ACCEPTED,
        payload={"step": "first"},
        created_at=NOW,
    )
    second_event = ChatRun.Event(
        id="a2aaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        run_id=run.id,
        event_type=ChatEventType.KNOWLEDGE_LOADED,
        payload={"step": "second"},
        created_at=NOW + timedelta(seconds=1),
    )

    repository.save_chat_session(session)
    repository.save_chat_message(first_message)
    repository.save_chat_message(second_message)
    repository.save_chat_run(run)
    repository.save_chat_run_event(first_event)
    repository.save_chat_run_event(second_event)

    assert repository.list_chat_messages(session.id, limit=1) == [first_message]
    assert repository.list_chat_run_events(run.id, limit=1) == [first_event]


def test_list_methods_reject_out_of_range_limits(repository: SQLiteRepository) -> None:
    calls = [
        lambda: repository.list_inspections(limit=0),
        lambda: repository.list_incidents(limit=0),
        lambda: repository.list_operations(limit=0),
        lambda: repository.list_chat_sessions(limit=0),
        lambda: repository.list_chat_messages("session", limit=0),
        lambda: repository.list_chat_run_events("run", limit=0),
        lambda: repository.list_inspections(limit=101),
        lambda: repository.list_incidents(limit=101),
        lambda: repository.list_operations(limit=101),
        lambda: repository.list_chat_sessions(limit=101),
        lambda: repository.list_chat_messages("session", limit=101),
        lambda: repository.list_chat_run_events("run", limit=101),
    ]

    for call in calls:
        with pytest.raises(StorageError) as raised:
            call()
        assert raised.value.code == "storage.invalid_limit"


def test_chat_read_queries_use_explicit_columns() -> None:
    methods = [
        SQLiteRepository.get_chat_session,
        SQLiteRepository.list_chat_sessions,
        SQLiteRepository.list_chat_messages,
        SQLiteRepository.get_chat_run,
        SQLiteRepository.list_chat_run_events,
    ]

    for method in methods:
        assert "SELECT *" not in inspect.getsource(method).upper()


def test_list_incidents_and_operations_are_limited(repository: SQLiteRepository) -> None:
    older_incident = Incident(
        id="abababab-abab-4aba-8aba-abababababab",
        title="Old kline delayed",
        symptom="Freshness was behind",
        severity=Severity.INFO,
        opened_at=NOW - timedelta(minutes=10),
        updated_at=NOW - timedelta(minutes=10),
    )
    newest_incident = Incident(
        id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        title="Kline delayed",
        symptom="Freshness is behind",
        severity=Severity.WARNING,
        opened_at=NOW,
        updated_at=NOW,
    )
    older_operation = Operation(
        id="cdcdcdcd-cdcd-4cdc-8cdc-cdcdcdcdcdcd",
        name="simulate_old_restart_preview",
        version="1",
        risk=OperationRisk.L1,
        requester="operator",
        requested_at=NOW - timedelta(minutes=10),
    )
    newest_operation = Operation(
        id="cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        name="simulate_restart_preview",
        version="1",
        risk=OperationRisk.L1,
        requester="operator",
        requested_at=NOW,
    )

    repository.save_incident(older_incident)
    repository.save_incident(newest_incident)
    repository.save_operation(older_operation)
    repository.save_operation(newest_operation)

    assert repository.list_incidents(limit=1) == [newest_incident]
    assert repository.list_operations(limit=1) == [newest_operation]


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
