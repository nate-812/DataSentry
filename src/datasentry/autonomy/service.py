"""有限自治服务编排。"""

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Protocol

from pydantic import JsonValue

from datasentry.autonomy.models import (
    AutonomyDecision,
    AutonomyDecisionStatus,
    AutonomyPolicy,
    AutonomyRunRecord,
    RateLimitRule,
)
from datasentry.autonomy.policy import AutonomyPolicyEngine
from datasentry.domain import Operation, OperationStatus
from datasentry.domain.common import utc_now
from datasentry.runbooks import Runbook, RunbookOperationService

AUTONOMY_ACTOR = "datasentry-autonomy"


class AutonomyRepository(Protocol):
    def get_autonomy_policy(self, runbook_name: str) -> AutonomyPolicy:
        raise NotImplementedError  # pragma: no cover

    def save_autonomy_run(self, record: AutonomyRunRecord) -> None:
        raise NotImplementedError  # pragma: no cover

    def update_autonomy_run(self, record: AutonomyRunRecord) -> None:
        raise NotImplementedError  # pragma: no cover

    def count_recent_allowed_autonomy_runs(
        self,
        *,
        runbook_name: str,
        target: str | None,
        incident_id: str | None,
        since: datetime,
    ) -> int:
        raise NotImplementedError  # pragma: no cover


class RunbookCatalog(Protocol):
    def get(self, name: str) -> Runbook:
        raise NotImplementedError  # pragma: no cover


class RunbookOperationServiceLike(Protocol):
    def request(
        self,
        runbook_name: str,
        parameters: dict[str, JsonValue],
        requester: str,
        incident_id: str | None = None,
    ) -> Operation:
        raise NotImplementedError  # pragma: no cover

    def approve(self, operation_id: str, approver: str) -> Operation:
        raise NotImplementedError  # pragma: no cover

    def execute(self, operation_id: str, actor: str) -> Operation:
        raise NotImplementedError  # pragma: no cover


class AutonomyService:
    """评估自治候选，并在允许时复用 M6 Runbook 执行闭环。"""

    def __init__(
        self,
        *,
        repository: AutonomyRepository,
        runbook_catalog: RunbookCatalog,
        runbook_operation_service: RunbookOperationService | RunbookOperationServiceLike,
        policy_engine: AutonomyPolicyEngine | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._repository = repository
        self._runbook_catalog = runbook_catalog
        self._runbook_operation_service = runbook_operation_service
        self._policy_engine = policy_engine or AutonomyPolicyEngine(clock=clock)
        self._clock = clock

    def evaluate_candidate(
        self,
        runbook_name: str,
        *,
        parameters: dict[str, JsonValue],
        incident_id: str | None,
    ) -> AutonomyDecision:
        policy = self._repository.get_autonomy_policy(runbook_name)
        runbook = self._runbook_catalog.get(runbook_name)
        decision = self._policy_engine.evaluate(
            policy=policy,
            runbook=runbook,
            parameters=parameters,
            incident_id=incident_id,
        )
        if decision.status is not AutonomyDecisionStatus.ALLOWED:
            return decision
        return self._apply_rate_limits(policy, decision)

    def execute_candidate(
        self,
        runbook_name: str,
        *,
        parameters: dict[str, JsonValue],
        incident_id: str | None,
    ) -> AutonomyDecision:
        decision = self.evaluate_candidate(
            runbook_name,
            parameters=parameters,
            incident_id=incident_id,
        )
        if decision.status is not AutonomyDecisionStatus.ALLOWED:
            self._repository.save_autonomy_run(self._record_from_decision(decision))
            return decision

        operation = self._runbook_operation_service.request(
            runbook_name,
            parameters=parameters,
            requester=AUTONOMY_ACTOR,
            incident_id=incident_id,
        )
        approved = self._runbook_operation_service.approve(
            operation.id,
            approver=AUTONOMY_ACTOR,
        )
        executed = self._runbook_operation_service.execute(
            approved.id,
            actor=AUTONOMY_ACTOR,
        )
        final_decision = decision.model_copy(update={"operation_id": executed.id})
        record = self._record_from_decision(
            final_decision,
            succeeded=executed.status is OperationStatus.SUCCEEDED,
        )
        self._repository.save_autonomy_run(record)
        return final_decision

    def _apply_rate_limits(
        self,
        policy: AutonomyPolicy,
        decision: AutonomyDecision,
    ) -> AutonomyDecision:
        for rule in policy.rate_limits:
            count = self._count_for_rate_limit(rule, decision)
            if count >= rule.limit:
                return decision.model_copy(
                    update={
                        "status": AutonomyDecisionStatus.ESCALATED,
                        "reason_code": "policy.rate_limit_exceeded",
                        "reason": "自治速率限制已达到，升级人工审批",
                    },
                )
        return decision

    def _count_for_rate_limit(
        self,
        rule: RateLimitRule,
        decision: AutonomyDecision,
    ) -> int:
        since = self._clock() - timedelta(seconds=rule.window_seconds)
        target = decision.target if rule.scope in {"per_target"} else None
        incident_id = decision.incident_id if rule.scope in {"per_incident"} else None
        return self._repository.count_recent_allowed_autonomy_runs(
            runbook_name=decision.runbook_name,
            target=target,
            incident_id=incident_id,
            since=since,
        )

    def _record_from_decision(
        self,
        decision: AutonomyDecision,
        *,
        succeeded: bool | None = None,
    ) -> AutonomyRunRecord:
        return AutonomyRunRecord(
            runbook_name=decision.runbook_name,
            target=decision.target or "unknown",
            incident_id=decision.incident_id,
            operation_id=decision.operation_id,
            decision_status=decision.status,
            reason_code=decision.reason_code,
            reason=decision.reason,
            created_at=self._clock(),
            finished_at=self._clock() if succeeded is not None else None,
            succeeded=succeeded,
            payload=decision.payload,
        )
