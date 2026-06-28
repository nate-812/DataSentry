"""Incident 读取路由。"""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder

from datasentry.api.dependencies import get_repository
from datasentry.domain import IncidentStatus
from datasentry.storage import SQLiteRepository

router = APIRouter(tags=["incidents"])


@router.get("/incidents")
def list_incidents(
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
    status: IncidentStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[dict[str, object]]:
    return cast(
        list[dict[str, object]],
        jsonable_encoder(repository.list_incidents(status=status, limit=limit)),
    )


@router.get("/incidents/{incident_id}")
def get_incident(
    incident_id: str,
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> dict[str, object]:
    return cast(dict[str, object], jsonable_encoder(repository.get_incident(incident_id)))
