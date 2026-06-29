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
from datasentry.autonomy import AutonomyService
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
