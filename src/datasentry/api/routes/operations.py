"""Runbook Operation 路由。"""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query, status
from fastapi.encoders import jsonable_encoder
from pydantic import JsonValue

from datasentry.api.dependencies import (
    get_repository,
    get_runbook_catalog,
    get_runbook_operation_service,
)
from datasentry.api.schemas import (
    OperationActionRequest,
    OperationCancelRequest,
    OperationCreateRequest,
    OperationExecuteRequest,
    OperationSimulationRequest,
)
from datasentry.domain import OperationStatus
from datasentry.errors import DataSentryError
from datasentry.runbooks import BuiltInRunbookCatalog, Runbook, RunbookOperationService
from datasentry.storage import SQLiteRepository

router = APIRouter(tags=["operations"])


@router.get("/operations")
def list_operations(
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
    status_filter: Annotated[OperationStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[dict[str, object]]:
    return cast(
        list[dict[str, object]],
        jsonable_encoder(repository.list_operations(status=status_filter, limit=limit)),
    )


@router.get("/operations/{operation_id}")
def get_operation(
    operation_id: str,
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> dict[str, object]:
    return cast(dict[str, object], jsonable_encoder(repository.get_operation(operation_id)))


@router.post("/operations", status_code=status.HTTP_201_CREATED)
def create_operation(
    request: OperationCreateRequest,
    catalog: Annotated[BuiltInRunbookCatalog, Depends(get_runbook_catalog)],
    service: Annotated[RunbookOperationService, Depends(get_runbook_operation_service)],
) -> dict[str, object]:
    runbook = catalog.get(request.runbook_name)
    _validate_required_parameters(runbook, request.parameters)
    operation = service.request(
        request.runbook_name,
        parameters=request.parameters,
        requester=request.requester,
        incident_id=request.incident_id,
    )
    return cast(dict[str, object], jsonable_encoder(operation))


@router.post("/operations/simulations", status_code=status.HTTP_201_CREATED)
def create_simulation_operation(
    request: OperationSimulationRequest,
    service: Annotated[RunbookOperationService, Depends(get_runbook_operation_service)],
) -> dict[str, object]:
    if not request.name.startswith("simulate_"):
        raise DataSentryError(
            code="operation.not_simulation",
            message="M4 只允许创建本地模拟审批操作",
        )
    runbook_name = "mock.clear_cache_preview" if "cache" in request.name else "mock.restart_preview"
    operation = service.request(
        runbook_name,
        parameters={"target": request.name, "reason": "本地模拟审批"},
        requester=request.requester,
    )
    return cast(dict[str, object], jsonable_encoder(operation))


@router.post("/operations/{operation_id}/approve")
def approve_operation(
    operation_id: str,
    request: OperationActionRequest,
    service: Annotated[RunbookOperationService, Depends(get_runbook_operation_service)],
) -> dict[str, object]:
    return cast(
        dict[str, object],
        jsonable_encoder(service.approve(operation_id, approver=request.approver)),
    )


@router.post("/operations/{operation_id}/reject")
def reject_operation(
    operation_id: str,
    request: OperationActionRequest,
    service: Annotated[RunbookOperationService, Depends(get_runbook_operation_service)],
) -> dict[str, object]:
    return cast(
        dict[str, object],
        jsonable_encoder(service.reject(operation_id, approver=request.approver)),
    )


@router.post("/operations/{operation_id}/execute")
def execute_operation(
    operation_id: str,
    request: OperationExecuteRequest,
    service: Annotated[RunbookOperationService, Depends(get_runbook_operation_service)],
) -> dict[str, object]:
    return cast(
        dict[str, object],
        jsonable_encoder(service.execute(operation_id, actor=request.actor)),
    )


@router.post("/operations/{operation_id}/cancel")
def cancel_operation(
    operation_id: str,
    request: OperationCancelRequest,
    service: Annotated[RunbookOperationService, Depends(get_runbook_operation_service)],
) -> dict[str, object]:
    return cast(
        dict[str, object],
        jsonable_encoder(service.cancel(operation_id, actor=request.actor)),
    )


@router.get("/operations/{operation_id}/events")
def list_operation_events(
    operation_id: str,
    service: Annotated[RunbookOperationService, Depends(get_runbook_operation_service)],
) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], jsonable_encoder(service.events(operation_id)))


def _validate_required_parameters(
    runbook: Runbook,
    parameters: dict[str, JsonValue],
) -> None:
    required_parameters = runbook.parameter_schema.get("required", [])
    if not isinstance(required_parameters, list):
        return
    properties = runbook.parameter_schema.get("properties", {})

    for parameter in required_parameters:
        if not isinstance(parameter, str):
            continue
        value = parameters.get(parameter)
        if _required_parameter_is_invalid(parameter, value, properties):
            raise DataSentryError(
                code="runbook.invalid_parameters",
                message=f"Runbook 参数缺少 {parameter}",
                details={"parameter": parameter},
            )


def _required_parameter_is_invalid(
    parameter: str,
    value: JsonValue | None,
    properties: JsonValue,
) -> bool:
    if value is None:
        return True
    if isinstance(properties, dict):
        schema = properties.get(parameter)
        if isinstance(schema, dict) and schema.get("type") == "string":
            return not isinstance(value, str) or not value.strip()
    return isinstance(value, str) and not value.strip()
