"""FastAPI 路由依赖。"""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request

from datasentry.config import Settings
from datasentry.operations import SimulationOperationService
from datasentry.storage import SQLiteRepository


def get_settings(request: Request) -> Settings:
    settings = request.app.state.settings
    assert isinstance(settings, Settings)
    return settings


def get_repository(
    settings: Annotated[Settings, Depends(get_settings)],
) -> Iterator[SQLiteRepository]:
    with SQLiteRepository(settings.database_path) as repository:
        yield repository


def get_simulation_service(
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> SimulationOperationService:
    return SimulationOperationService(repository=repository)
