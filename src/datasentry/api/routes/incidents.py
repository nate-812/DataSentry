"""Incident 读取路由。"""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import PlainTextResponse

from datasentry.api.dependencies import get_incident_service, get_repository
from datasentry.domain import IncidentStatus
from datasentry.incidents import IncidentService
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
    incident_service: Annotated[IncidentService, Depends(get_incident_service)],
) -> dict[str, object]:
    return cast(dict[str, object], jsonable_encoder(incident_service.get_detail(incident_id)))


@router.get("/incidents/{incident_id}/timeline")
def list_incident_timeline(
    incident_id: str,
    incident_service: Annotated[IncidentService, Depends(get_incident_service)],
) -> list[dict[str, object]]:
    return cast(
        list[dict[str, object]],
        jsonable_encoder(incident_service.get_detail(incident_id).timeline),
    )


@router.get("/incidents/{incident_id}/similar")
def list_similar_incidents(
    incident_id: str,
    incident_service: Annotated[IncidentService, Depends(get_incident_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 5,
) -> list[dict[str, object]]:
    return cast(
        list[dict[str, object]],
        jsonable_encoder(incident_service.find_similar(incident_id, limit=limit)),
    )


@router.post("/incidents/{incident_id}/rca")
def generate_incident_rca(
    incident_id: str,
    incident_service: Annotated[IncidentService, Depends(get_incident_service)],
) -> dict[str, object]:
    return cast(dict[str, object], jsonable_encoder(incident_service.generate_rca(incident_id)))


@router.get("/incidents/{incident_id}/export")
def export_incident_rca(
    incident_id: str,
    incident_service: Annotated[IncidentService, Depends(get_incident_service)],
) -> PlainTextResponse:
    detail = incident_service.get_detail(incident_id)
    report = detail.latest_rca or incident_service.generate_rca(incident_id)
    return PlainTextResponse(
        report.markdown,
        media_type="text/markdown; charset=utf-8",
    )
