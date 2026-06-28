"""对话诊断编排服务。"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Protocol

from pydantic import Field, JsonValue

from datasentry.chat.models import (
    ChatEventType,
    ChatMessage,
    ChatRole,
    ChatRun,
    ChatRunStatus,
    ChatSession,
)
from datasentry.domain import Finding, Inspection
from datasentry.domain.common import DomainModel, utc_now
from datasentry.llm import AnswerContext, AnswerSummarizer, AnswerSummary


class ChatRepository(Protocol):
    def save_chat_session(self, session: ChatSession) -> None:
        raise NotImplementedError  # pragma: no cover

    def save_chat_message(self, message: ChatMessage) -> None:
        raise NotImplementedError  # pragma: no cover

    def save_chat_run(self, run: ChatRun) -> None:
        raise NotImplementedError  # pragma: no cover

    def update_chat_run(self, run: ChatRun) -> None:
        raise NotImplementedError  # pragma: no cover

    def save_chat_run_event(self, event: ChatRun.Event) -> None:
        raise NotImplementedError  # pragma: no cover


class InspectionAggregateLike(Protocol):
    @property
    def inspection(self) -> Inspection:
        raise NotImplementedError  # pragma: no cover

    @property
    def findings(self) -> Sequence[Finding]:
        raise NotImplementedError  # pragma: no cover


class DiagnosisResultLike(Protocol):
    @property
    def aggregate(self) -> InspectionAggregateLike:
        raise NotImplementedError  # pragma: no cover


class LiveInspectionResultLike(Protocol):
    @property
    def diagnosis(self) -> DiagnosisResultLike:
        raise NotImplementedError  # pragma: no cover

    @property
    def tool_invocations(self) -> Sequence[object]:
        raise NotImplementedError  # pragma: no cover


class LiveInspectionRunner(Protocol):
    def run(self, question: str) -> LiveInspectionResultLike:
        raise NotImplementedError  # pragma: no cover


class AnswerSummarizerLike(Protocol):
    def summarize(self, context: AnswerContext) -> AnswerSummary:
        raise NotImplementedError  # pragma: no cover


class ChatRunResult(DomainModel):
    run: ChatRun
    user_message: ChatMessage
    assistant_message: ChatMessage
    event_count: int = Field(ge=0)


class ChatService:
    """把用户问题编排为可追踪的只读诊断任务。"""

    def __init__(
        self,
        *,
        repository: ChatRepository,
        live_inspection: LiveInspectionRunner,
        summarizer: AnswerSummarizer | AnswerSummarizerLike,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._repository = repository
        self._live_inspection = live_inspection
        self._summarizer = summarizer
        self._clock = clock

    def create_session(self, *, title: str) -> ChatSession:
        now = self._clock()
        session = ChatSession(title=title, created_at=now, updated_at=now)
        self._repository.save_chat_session(session)
        return session

    def run_question(self, session_id: str, question: str) -> ChatRunResult:
        now = self._clock()
        user_message = ChatMessage(
            session_id=session_id,
            role=ChatRole.USER,
            content=question,
            created_at=now,
        )
        self._repository.save_chat_message(user_message)
        run = ChatRun(
            session_id=session_id,
            user_message_id=user_message.id,
            created_at=now,
        )
        self._repository.save_chat_run(run)
        event_count = 0

        def emit(event_type: ChatEventType, payload: dict[str, JsonValue]) -> None:
            nonlocal event_count
            self._repository.save_chat_run_event(
                ChatRun.Event(
                    run_id=run.id,
                    event_type=event_type,
                    payload=payload,
                    created_at=self._clock(),
                )
            )
            event_count += 1

        try:
            emit(ChatEventType.ACCEPTED, {"question": question})
            emit(ChatEventType.TOOLS_PLANNED, {"source": "live_inspection_service"})
            live_result = self._live_inspection.run(question)
            aggregate = live_result.diagnosis.aggregate
            findings = list(aggregate.findings)
            emit(ChatEventType.RULES_COMPLETED, {"finding_count": len(findings)})
            emit(ChatEventType.LLM_STARTED, {"provider": "configured"})
            summary = self._summarizer.summarize(
                AnswerContext(
                    question=question,
                    findings=findings,
                    tool_invocation_count=len(live_result.tool_invocations),
                )
            )
            emit(ChatEventType.LLM_COMPLETED, {"llm_status": summary.llm_status})
            assistant_message = ChatMessage(
                session_id=session_id,
                role=ChatRole.ASSISTANT,
                content=summary.content,
                inspection_id=aggregate.inspection.id,
                llm_status=summary.llm_status,
                created_at=self._clock(),
            )
            self._repository.save_chat_message(assistant_message)
            completed = run.model_copy(
                update={
                    "status": ChatRunStatus.COMPLETED,
                    "inspection_id": aggregate.inspection.id,
                    "finished_at": self._clock(),
                }
            )
            self._repository.update_chat_run(completed)
            emit(ChatEventType.COMPLETED, {"inspection_id": aggregate.inspection.id})
            return ChatRunResult(
                run=completed,
                user_message=user_message,
                assistant_message=assistant_message,
                event_count=event_count,
            )
        except Exception as error:
            failed = run.model_copy(
                update={
                    "status": ChatRunStatus.FAILED,
                    "error_code": getattr(error, "code", "internal.error"),
                    "error_message": "对话诊断失败",
                    "finished_at": self._clock(),
                }
            )
            self._repository.update_chat_run(failed)
            emit(
                ChatEventType.FAILED,
                {"code": failed.error_code, "message": failed.error_message},
            )
            raise
