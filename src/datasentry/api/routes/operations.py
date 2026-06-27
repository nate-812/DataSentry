"""本地模拟审批 Operation 路由。"""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query, status
from fastapi.encoders import jsonable_encoder

from datasentry.api.dependencies import get_repository, get_simulation_service
from datasentry.api.schemas import OperationActionRequest, OperationSimulationRequest
from datasentry.domain import Operation, OperationRisk, OperationStatus
from datasentry.errors import DataSentryError
from datasentry.operations import SimulationOperationService
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


@router.post("/operations/simulations", status_code=status.HTTP_201_CREATED)
def create_simulation_operation(
    request: OperationSimulationRequest,
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> dict[str, object]:
    if not request.name.startswith("simulate_"):
        raise DataSentryError(
            code="operation.not_simulation",
            message="M4 只允许创建本地模拟审批操作",
        )
    operation = Operation(
        name=request.name,
        version="m4-simulation",
        risk=OperationRisk.L1,
        requester=request.requester,
    )
    repository.save_operation(operation)
    return cast(dict[str, object], jsonable_encoder(operation))


@router.post("/operations/{operation_id}/approve")
def approve_operation(
    operation_id: str,
    request: OperationActionRequest,
    service: Annotated[SimulationOperationService, Depends(get_simulation_service)],
) -> dict[str, object]:
    return cast(
        dict[str, object],
        jsonable_encoder(service.approve(operation_id, approver=request.approver)),
    )


@router.post("/operations/{operation_id}/reject")
def reject_operation(
    operation_id: str,
    request: OperationActionRequest,
    service: Annotated[SimulationOperationService, Depends(get_simulation_service)],
) -> dict[str, object]:
    return cast(
        dict[str, object],
        jsonable_encoder(service.reject(operation_id, approver=request.approver)),
    )
