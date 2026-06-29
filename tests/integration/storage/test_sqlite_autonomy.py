from datetime import UTC, datetime, timedelta
from pathlib import Path

from datasentry.autonomy import (
    AutonomyDecisionStatus,
    AutonomyPolicy,
    AutonomyRunRecord,
    CircuitBreakerState,
)
from datasentry.storage import SQLiteRepository, upgrade_database


def _repository(tmp_path: Path) -> SQLiteRepository:
    database_path = tmp_path / "datasentry.db"
    upgrade_database(database_path)
    return SQLiteRepository(database_path)


def test_repository_saves_and_loads_autonomy_policy(tmp_path: Path) -> None:
    with _repository(tmp_path) as repository:
        policy = AutonomyPolicy(
            runbook_name="mock.restart_preview",
            enabled=True,
            shadow_mode=False,
            circuit_breaker_state=CircuitBreakerState.HALF_OPEN,
        )

        repository.save_autonomy_policy(policy)
        loaded = repository.get_autonomy_policy("mock.restart_preview")

    assert loaded.runbook_name == "mock.restart_preview"
    assert loaded.enabled is True
    assert loaded.shadow_mode is False
    assert loaded.circuit_breaker_state is CircuitBreakerState.HALF_OPEN


def test_repository_lists_autonomy_policies_by_runbook_name(tmp_path: Path) -> None:
    with _repository(tmp_path) as repository:
        repository.save_autonomy_policy(AutonomyPolicy(runbook_name="mock.restart_preview"))
        repository.save_autonomy_policy(AutonomyPolicy(runbook_name="mock.clear_cache_preview"))

        policies = repository.list_autonomy_policies()

    assert [policy.runbook_name for policy in policies] == [
        "mock.clear_cache_preview",
        "mock.restart_preview",
    ]


def test_repository_records_autonomy_run_and_lists_recent_runs(tmp_path: Path) -> None:
    with _repository(tmp_path) as repository:
        record = AutonomyRunRecord(
            runbook_name="mock.restart_preview",
            target="api",
            decision_status=AutonomyDecisionStatus.SHADOWED,
            reason_code="policy.shadow_mode",
            reason="自治策略处于 shadow 模式，仅记录不执行",
            created_at=datetime(2026, 6, 29, 2, 0, tzinfo=UTC),
        )

        repository.save_autonomy_run(record)
        runs = repository.list_autonomy_runs(limit=10)

    assert len(runs) == 1
    assert runs[0].id == record.id
    assert runs[0].decision_status is AutonomyDecisionStatus.SHADOWED


def test_repository_updates_autonomy_run_result(tmp_path: Path) -> None:
    with _repository(tmp_path) as repository:
        record = AutonomyRunRecord(
            runbook_name="mock.restart_preview",
            target="api",
            operation_id="operation-1",
            decision_status=AutonomyDecisionStatus.ALLOWED,
            reason_code="policy.allowed",
            reason="自治策略允许 mock 自动执行",
        )
        repository.save_autonomy_run(record)

        finished = record.model_copy(
            update={
                "finished_at": datetime(2026, 6, 29, 2, 1, tzinfo=UTC),
                "succeeded": True,
            },
        )
        repository.update_autonomy_run(finished)
        runs = repository.list_autonomy_runs(limit=1)

    assert runs[0].succeeded is True


def test_repository_counts_recent_allowed_autonomy_runs(tmp_path: Path) -> None:
    now = datetime(2026, 6, 29, 2, 0, tzinfo=UTC)
    with _repository(tmp_path) as repository:
        recent = AutonomyRunRecord(
            runbook_name="mock.restart_preview",
            target="api",
            incident_id="incident-1",
            operation_id="operation-1",
            decision_status=AutonomyDecisionStatus.ALLOWED,
            reason_code="policy.allowed",
            reason="自治策略允许 mock 自动执行",
            created_at=now,
        )
        old = recent.model_copy(
            update={
                "id": "old-run",
                "operation_id": "operation-2",
                "created_at": now - timedelta(hours=2),
            },
        )
        shadow = recent.model_copy(
            update={
                "id": "shadow-run",
                "operation_id": None,
                "decision_status": AutonomyDecisionStatus.SHADOWED,
                "created_at": now,
            },
        )
        repository.save_autonomy_run(recent)
        repository.save_autonomy_run(old)
        repository.save_autonomy_run(shadow)

        count = repository.count_recent_allowed_autonomy_runs(
            runbook_name="mock.restart_preview",
            target="api",
            incident_id="incident-1",
            since=now - timedelta(minutes=30),
        )

    assert count == 1
