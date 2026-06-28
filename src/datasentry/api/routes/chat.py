"""聊天诊断 API 和 SSE 事件回放。"""

from collections.abc import Iterator
from typing import Annotated, cast

from fastapi import APIRouter, Depends, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse

from datasentry.api.dependencies import get_chat_service, get_repository
from datasentry.api.schemas import ChatRunCreateRequest, ChatSessionCreateRequest
from datasentry.api.sse import encode_sse
from datasentry.chat import ChatService, ChatSession
from datasentry.storage import SQLiteRepository

router = APIRouter(tags=["chat"])


@router.post("/chat/sessions", status_code=status.HTTP_201_CREATED)
def create_chat_session(
    request: ChatSessionCreateRequest,
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> dict[str, object]:
    session = ChatSession(title=request.title)
    repository.save_chat_session(session)
    return cast(dict[str, object], jsonable_encoder(session))


@router.get("/chat/sessions")
def list_chat_sessions(
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], jsonable_encoder(repository.list_chat_sessions()))


@router.get("/chat/sessions/{session_id}")
def get_chat_session(
    session_id: str,
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> dict[str, object]:
    return {
        "session": cast(
            dict[str, object],
            jsonable_encoder(repository.get_chat_session(session_id)),
        ),
        "messages": cast(
            list[dict[str, object]],
            jsonable_encoder(repository.list_chat_messages(session_id, limit=100)),
        ),
    }


@router.post("/chat/sessions/{session_id}/runs")
def run_chat_question(
    session_id: str,
    request: ChatRunCreateRequest,
    service: Annotated[ChatService, Depends(get_chat_service)],
) -> dict[str, object]:
    result = service.run_question(session_id, request.question)
    return cast(dict[str, object], jsonable_encoder(result))


@router.get("/chat/runs/{run_id}")
def get_chat_run(
    run_id: str,
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> dict[str, object]:
    run = repository.get_chat_run(run_id)
    messages = repository.list_chat_messages(run.session_id, limit=100)
    return {
        "run": cast(dict[str, object], jsonable_encoder(run)),
        "messages": cast(list[dict[str, object]], jsonable_encoder(messages)),
    }


@router.get("/chat/runs/{run_id}/events")
def stream_chat_run_events(
    run_id: str,
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> StreamingResponse:
    events = repository.list_chat_run_events(run_id, limit=100)

    def iter_events() -> Iterator[str]:
        for event in events:
            yield encode_sse(event.event_type.value, dict(event.payload))

    return StreamingResponse(iter_events(), media_type="text/event-stream")
