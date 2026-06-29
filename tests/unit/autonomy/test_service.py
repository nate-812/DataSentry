from datetime import UTC, datetime

from datasentry.autonomy import (
    AutonomyDecisionStatus,
    AutonomyPolicy,
    AutonomyRunRecord,
    RateLimitRule,
)
from datasentry.autonomy.service import AutonomyService
from datasentry.domain import Operation, OperationRisk, OperationStatus
from datasentry.runbooks import BuiltInRunbookCatalog

NOW = datetime(2026, 6, 29, 2, 0, tzinfo=UTC)


class FakeAutonomyRepository:
    def __init__(self, policy: AutonomyPolicy, recent_allowed_count: int = 0) -> None:
        self.policy = policy
        self.recent_allowed_count = recent_allowed_count
        self.runs: list[AutonomyRunRecord] = []

    def get_autonomy_policy(self, runbook_name: str) -> AutonomyPolicy:
        return self.policy.model_copy(deep=True)

    def save_autonomy_run(self, record: AutonomyRunRecord) -> None:
        self.runs.append(record.model_copy(deep=True))

    def update_autonomy_run(self, record: AutonomyRunRecord) -> None:
        self.runs[-1] = record.model_copy(deep=True)

    def count_recent_allowed_autonomy_runs(
        self,
        *,
        runbook_name: str,
        target: str | None,
        incident_id: str | None,
        since: datetime,
    ) -> int:
        del runbook_name, target, incident_id, since
        return self.recent_allowed_count


class FakeRunbookOperationService:
    def __init__(self) -> None:
        self.requested = False
        self.approved = False
        self.executed = False
        self.operation = Operation(
            id="operation-1",
            name="mock.restart_preview",
            version="1.0.0",
            parameters={"target": "api", "reason": "演练"},
            risk=OperationRisk.L1,
            status=OperationStatus.AWAITING_APPROVAL,
            requester="datasentry-autonomy",
            requested_at=NOW,
        )

    def request(
        self,
        runbook_name: str,
        parameters: dict[str, object],
        requester: str,
        incident_id: str | None = None,
    ) -> Operation:
        del runbook_name, parameters, requester, incident_id
        self.requested = True
        return self.operation

    def approve(self, operation_id: str, approver: str) -> Operation:
        del operation_id, approver
        self.approved = True
        self.operation = self.operation.model_copy(update={"status": OperationStatus.APPROVED})
        return self.operation

    def execute(self, operation_id: str, actor: str) -> Operation:
        del operation_id, actor
        self.executed = True
        self.operation = self.operation.model_copy(update={"status": OperationStatus.SUCCEEDED})
        return self.operation


def _service(
    repository: FakeAutonomyRepository,
    runbook_service: FakeRunbookOperationService,
) -> AutonomyService:
    return AutonomyService(
        repository=repository,
        runbook_catalog=BuiltInRunbookCatalog(),
        runbook_operation_service=runbook_service,
        clock=lambda: NOW,
    )


def test_shadow_decision_records_run_without_operation() -> None:
    repository = FakeAutonomyRepository(
        AutonomyPolicy(
            runbook_name="mock.restart_preview",
            enabled=True,
            shadow_mode=True,
        ),
    )
    runbook_service = FakeRunbookOperationService()
    service = _service(repository, runbook_service)

    decision = service.execute_candidate(
        "mock.restart_preview",
        parameters={"target": "api", "reason": "演练"},
        incident_id=None,
    )

    assert decision.status is AutonomyDecisionStatus.SHADOWED
    assert runbook_service.requested is False
    assert repository.runs[0].decision_status is AutonomyDecisionStatus.SHADOWED
    assert repository.runs[0].operation_id is None


def test_allowed_decision_delegates_to_runbook_service() -> None:
    repository = FakeAutonomyRepository(
        AutonomyPolicy(
            runbook_name="mock.restart_preview",
            enabled=True,
            shadow_mode=False,
        ),
    )
    runbook_service = FakeRunbookOperationService()
    service = _service(repository, runbook_service)

    decision = service.execute_candidate(
        "mock.restart_preview",
        parameters={"target": "api", "reason": "演练"},
        incident_id="incident-1",
    )

    assert decision.status is AutonomyDecisionStatus.ALLOWED
    assert decision.operation_id == "operation-1"
    assert runbook_service.requested is True
    assert runbook_service.approved is True
    assert runbook_service.executed is True
    assert repository.runs[-1].operation_id == "operation-1"
    assert repository.runs[-1].succeeded is True


def test_rate_limit_escalates_before_creating_operation() -> None:
    repository = FakeAutonomyRepository(
        AutonomyPolicy(
            runbook_name="mock.restart_preview",
            enabled=True,
            shadow_mode=False,
            rate_limits=[
                RateLimitRule(scope="per_runbook", window_seconds=3600, limit=1),
            ],
        ),
        recent_allowed_count=1,
    )
    runbook_service = FakeRunbookOperationService()
    service = _service(repository, runbook_service)

    decision = service.execute_candidate(
        "mock.restart_preview",
        parameters={"target": "api", "reason": "演练"},
        incident_id=None,
    )

    assert decision.status is AutonomyDecisionStatus.ESCALATED
    assert decision.reason_code == "policy.rate_limit_exceeded"
    assert runbook_service.requested is False
    assert repository.runs[0].decision_status is AutonomyDecisionStatus.ESCALATED
