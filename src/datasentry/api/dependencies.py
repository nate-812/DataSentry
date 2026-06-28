"""FastAPI 路由依赖。"""

from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Request

from datasentry.chat import ChatService
from datasentry.config import Settings
from datasentry.incidents import IncidentService
from datasentry.llm import (
    AnswerSummarizer,
    DisabledLLMProvider,
    LLMProvider,
    MockLLMProvider,
    OpenAICompatibleProvider,
)
from datasentry.operations import SimulationOperationService
from datasentry.storage import SQLiteRepository
from datasentry.tools import TargetCatalog, build_live_inspection_service


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


def build_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "mock":
        return MockLLMProvider()
    if settings.llm_provider == "openai_compatible":
        if (
            settings.llm_base_url is None
            or settings.llm_model is None
            or settings.llm_api_key is None
        ):
            return DisabledLLMProvider()
        return OpenAICompatibleProvider(
            base_url=str(settings.llm_base_url),
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    return DisabledLLMProvider()


def get_chat_service(
    settings: Annotated[Settings, Depends(get_settings)],
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> ChatService:
    targets = TargetCatalog.load(settings.targets_file)
    live_inspection = build_live_inspection_service(
        repository=repository,
        targets=targets,
        knowledge_root=Path("knowledge"),
    )
    summarizer = AnswerSummarizer(provider=build_llm_provider(settings))
    return ChatService(
        repository=repository,
        live_inspection=live_inspection,
        summarizer=summarizer,
    )


def get_incident_service(
    settings: Annotated[Settings, Depends(get_settings)],
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> IncidentService:
    targets = TargetCatalog.load(settings.targets_file)
    live_inspection = build_live_inspection_service(
        repository=repository,
        targets=targets,
        knowledge_root=Path("knowledge"),
    )
    return IncidentService(repository=repository, diagnosis_runner=live_inspection)
