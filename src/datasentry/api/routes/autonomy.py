"""有限自治 API。"""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder

from datasentry.api.dependencies import (
    ensure_default_autonomy_policies,
    get_autonomy_service,
    get_repository,
)
from datasentry.api.schemas import AutonomyCandidateRequest, AutonomyPolicyUpdateRequest
from datasentry.autonomy import (
    AutonomyDecisionStatus,
    AutonomyPolicy,
    AutonomyRunRecord,
    AutonomyService,
    CircuitBreakerState,
)
from datasentry.domain.common import utc_now
from datasentry.storage import SQLiteRepository

router = APIRouter(prefix="/autonomy", tags=["autonomy"])


@router.get("/policies")
def list_autonomy_policies(
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> list[dict[str, object]]:
    ensure_default_autonomy_policies(repository)
    return cast(
        list[dict[str, object]],
        jsonable_encoder(repository.list_autonomy_policies()),
    )


@router.get("/policies/{runbook_name}")
def get_autonomy_policy(
    runbook_name: str,
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> dict[str, object]:
    ensure_default_autonomy_policies(repository)
    return cast(
        dict[str, object],
        jsonable_encoder(repository.get_autonomy_policy(runbook_name)),
    )


@router.patch("/policies/{runbook_name}")
def update_autonomy_policy(
    runbook_name: str,
    request: AutonomyPolicyUpdateRequest,
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> dict[str, object]:
    ensure_default_autonomy_policies(repository)
    policy = repository.get_autonomy_policy(runbook_name)
    updates: dict[str, object] = {}
    if request.enabled is not None:
        updates["enabled"] = request.enabled
    if request.shadow_mode is not None:
        updates["shadow_mode"] = request.shadow_mode
    updated = policy.model_copy(update=updates)
    repository.save_autonomy_policy(updated)
    return cast(dict[str, object], jsonable_encoder(updated))


@router.get("/stats")
def list_autonomy_stats(
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> list[dict[str, object]]:
    ensure_default_autonomy_policies(repository)
    policies = repository.list_autonomy_policies()
    runs = repository.list_autonomy_runs(limit=limit)
    return [_stats_for_policy(policy, runs) for policy in policies]


@router.post("/evaluate")
def evaluate_autonomy_candidate(
    request: AutonomyCandidateRequest,
    service: Annotated[AutonomyService, Depends(get_autonomy_service)],
) -> dict[str, object]:
    decision = service.evaluate_candidate(
        request.runbook_name,
        parameters=request.parameters,
        incident_id=request.incident_id,
    )
    return cast(dict[str, object], jsonable_encoder(decision))


@router.post("/execute")
def execute_autonomy_candidate(
    request: AutonomyCandidateRequest,
    service: Annotated[AutonomyService, Depends(get_autonomy_service)],
) -> dict[str, object]:
    decision = service.execute_candidate(
        request.runbook_name,
        parameters=request.parameters,
        incident_id=request.incident_id,
    )
    return cast(dict[str, object], jsonable_encoder(decision))


@router.get("/runs")
def list_autonomy_runs(
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[dict[str, object]]:
    return cast(
        list[dict[str, object]],
        jsonable_encoder(repository.list_autonomy_runs(limit=limit)),
    )


@router.post("/circuit-breakers/{runbook_name}/reset")
def reset_autonomy_circuit_breaker(
    runbook_name: str,
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> dict[str, object]:
    return _set_circuit_breaker_state(
        repository,
        runbook_name,
        CircuitBreakerState.CLOSED,
    )


@router.post("/circuit-breakers/{runbook_name}/half-open")
def half_open_autonomy_circuit_breaker(
    runbook_name: str,
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> dict[str, object]:
    return _set_circuit_breaker_state(
        repository,
        runbook_name,
        CircuitBreakerState.HALF_OPEN,
    )


def _set_circuit_breaker_state(
    repository: SQLiteRepository,
    runbook_name: str,
    state: CircuitBreakerState,
) -> dict[str, object]:
    ensure_default_autonomy_policies(repository)
    policy = repository.get_autonomy_policy(runbook_name)
    updated = policy.model_copy(
        update={
            "circuit_breaker_state": state,
            "updated_at": utc_now(),
        },
    )
    repository.save_autonomy_policy(updated)
    return cast(dict[str, object], jsonable_encoder(updated))


def _stats_for_policy(
    policy: AutonomyPolicy,
    runs: list[AutonomyRunRecord],
) -> dict[str, object]:
    policy_runs = [run for run in runs if run.runbook_name == policy.runbook_name]
    allowed_runs = [
        run for run in policy_runs if run.decision_status is AutonomyDecisionStatus.ALLOWED
    ]
    successful_runs = [run for run in allowed_runs if run.succeeded is True]
    failed_runs = [run for run in allowed_runs if run.succeeded is False]
    success_rate = len(successful_runs) / len(allowed_runs) if allowed_runs else None
    ready_for_autonomy = (
        policy.enabled
        and not policy.shadow_mode
        and success_rate is not None
        and len(allowed_runs) >= policy.min_success_samples
        and success_rate >= policy.min_success_rate
        and policy.circuit_breaker_state is CircuitBreakerState.CLOSED
    )

    return {
        "runbook_name": policy.runbook_name,
        "enabled": policy.enabled,
        "shadow_mode": policy.shadow_mode,
        "circuit_breaker_state": policy.circuit_breaker_state.value,
        "total_runs": len(policy_runs),
        "allowed_runs": len(allowed_runs),
        "shadowed_runs": _count_runs(policy_runs, AutonomyDecisionStatus.SHADOWED),
        "blocked_runs": _count_runs(policy_runs, AutonomyDecisionStatus.BLOCKED),
        "escalated_runs": _count_runs(policy_runs, AutonomyDecisionStatus.ESCALATED),
        "successful_runs": len(successful_runs),
        "failed_runs": len(failed_runs),
        "success_rate": success_rate,
        "min_success_rate": policy.min_success_rate,
        "min_success_samples": policy.min_success_samples,
        "ready_for_autonomy": ready_for_autonomy,
        "last_decision_at": (policy_runs[0].created_at.isoformat() if policy_runs else None),
    }


def _count_runs(
    runs: list[AutonomyRunRecord],
    status: AutonomyDecisionStatus,
) -> int:
    return sum(1 for run in runs if run.decision_status is status)
