"""健康状态和 Command Center 概览路由。"""

from typing import Annotated, cast

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder

from datasentry.api.dependencies import get_repository, get_settings
from datasentry.api.schemas import DatabaseHealth, HealthResponse, LLMHealth, OverviewResponse
from datasentry.config import Settings
from datasentry.storage import SQLiteRepository

router = APIRouter(tags=["overview"])


@router.get("/health", response_model=HealthResponse)
def health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    return _health_response(settings)


@router.get("/overview", response_model=OverviewResponse)
def overview(
    settings: Annotated[Settings, Depends(get_settings)],
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> dict[str, object]:
    inspections = [
        {
            "inspection": aggregate.inspection,
            "observation_count": len(aggregate.observations),
            "finding_count": len(aggregate.findings),
        }
        for aggregate in repository.list_inspections(limit=10)
    ]
    return {
        "health": {"status": _health_response(settings).status},
        "recent_inspections": cast(list[dict[str, object]], jsonable_encoder(inspections)),
        "incidents": cast(
            list[dict[str, object]],
            jsonable_encoder(repository.list_incidents(limit=10)),
        ),
        "operations": cast(
            list[dict[str, object]],
            jsonable_encoder(repository.list_operations(limit=10)),
        ),
        "grafana": {"url": str(settings.grafana_url) if settings.grafana_url else None},
    }


def _health_response(settings: Settings) -> HealthResponse:
    return HealthResponse(
        status="ok",
        environment=settings.environment,
        database=DatabaseHealth(configured=True),
        llm=LLMHealth(provider=settings.llm_provider, configured=_llm_configured(settings)),
    )


def _llm_configured(settings: Settings) -> bool:
    if settings.llm_provider in {"disabled", "mock"}:
        return True
    return all(
        (
            settings.llm_base_url is not None,
            settings.llm_model is not None,
            settings.llm_api_key is not None,
        )
    )
