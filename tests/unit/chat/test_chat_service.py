from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from datasentry.chat import (
    ChatEventType,
    ChatRole,
    ChatRun,
    ChatRunStatus,
    ChatService,
)
from datasentry.domain import (
    Evidence,
    EvidenceStatus,
    Finding,
    Inspection,
    InspectionStatus,
    Severity,
)
from datasentry.errors import DataSentryError
from datasentry.llm import AnswerContext, AnswerSummary
from datasentry.storage import InspectionAggregate

NOW = datetime(2026, 6, 27, 8, 0, tzinfo=UTC)


@dataclass(frozen=True)
class FakeDiagnosis:
    aggregate: InspectionAggregate


@dataclass(frozen=True)
class FakeLiveInspectionResult:
    diagnosis: FakeDiagnosis
    tool_invocations: list[object]


class FakeRepository:
    def __init__(self) -> None:
        self.sessions = []
        self.messages = []
        self.runs: list[ChatRun] = []
        self.events = []

    def save_chat_session(self, session):
        self.sessions.append(session)

    def save_chat_message(self, message):
        self.messages.append(message)

    def save_chat_run(self, run):
        self.runs.append(run)

    def update_chat_run(self, run):
        self.runs.append(run)

    def save_chat_run_event(self, event):
        self.events.append(event)


class FakeLiveInspectionService:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.questions: list[str] = []

    def run(self, question: str) -> FakeLiveInspectionResult:
        self.questions.append(question)
        if self.fail:
            raise DataSentryError(code="diagnosis.failed", message="诊断失败")
        inspection = Inspection(
            question=question,
            status=InspectionStatus.COMPLETED,
            summary="Kline delayed",
            started_at=NOW,
            finished_at=NOW,
        )
        evidence = Evidence(
            claim="Flink Kline Job 已完成只读检查",
            status=EvidenceStatus.CONFIRMED,
            source="inspection",
            target="flink",
            observed_at=NOW,
            summary="Checkpoint 正常但 Doris 新鲜度滞后",
        )
        finding = Finding(
            inspection_id=inspection.id,
            severity=Severity.WARNING,
            status=EvidenceStatus.CONFIRMED,
            claim="Kline 数据停止推进",
            evidence=[evidence],
            impact="页面可能显示旧数据",
            recommendation="检查 Flink Job",
            unknowns=[],
            created_at=NOW,
        )
        return FakeLiveInspectionResult(
            diagnosis=FakeDiagnosis(
                aggregate=InspectionAggregate(inspection, [], [finding]),
            ),
            tool_invocations=[object(), object()],
        )


class FakeSummarizer:
    def __init__(self) -> None:
        self.contexts: list[AnswerContext] = []

    def summarize(self, context: AnswerContext) -> AnswerSummary:
        self.contexts.append(context)
        return AnswerSummary(content="当前结论：Kline 数据停止推进", llm_status="disabled")


def test_chat_service_records_user_assistant_run_and_events() -> None:
    repository = FakeRepository()
    live_inspection = FakeLiveInspectionService()
    summarizer = FakeSummarizer()
    service = ChatService(
        repository=repository,
        live_inspection=live_inspection,
        summarizer=summarizer,
        clock=lambda: NOW,
    )

    session = service.create_session(title="Kline")
    result = service.run_question(session.id, "为什么K线不更新")

    assert repository.sessions == [session]
    assert live_inspection.questions == ["为什么K线不更新"]
    assert summarizer.contexts[0].tool_invocation_count == 2
    assert summarizer.contexts[0].findings[0].claim == "Kline 数据停止推进"
    assert result.assistant_message.role is ChatRole.ASSISTANT
    assert result.assistant_message.content.startswith("当前结论")
    assert result.assistant_message.inspection_id == result.run.inspection_id
    assert result.assistant_message.llm_status == "disabled"
    assert result.run.status is ChatRunStatus.COMPLETED
    assert result.event_count == 6
    assert [event.event_type for event in repository.events] == [
        ChatEventType.ACCEPTED,
        ChatEventType.TOOLS_PLANNED,
        ChatEventType.RULES_COMPLETED,
        ChatEventType.LLM_STARTED,
        ChatEventType.LLM_COMPLETED,
        ChatEventType.COMPLETED,
    ]


def test_chat_service_records_failed_run_and_event() -> None:
    repository = FakeRepository()
    service = ChatService(
        repository=repository,
        live_inspection=FakeLiveInspectionService(fail=True),
        summarizer=FakeSummarizer(),
        clock=lambda: NOW,
    )
    session = service.create_session(title="Kline")

    with pytest.raises(DataSentryError):
        service.run_question(session.id, "为什么K线不更新")

    failed = repository.runs[-1]
    assert failed.status is ChatRunStatus.FAILED
    assert failed.error_code == "diagnosis.failed"
    assert failed.error_message == "对话诊断失败"
    assert repository.events[-1].event_type is ChatEventType.FAILED
    assert repository.events[-1].payload == {
        "code": "diagnosis.failed",
        "message": "对话诊断失败",
    }
