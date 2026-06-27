from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from datasentry.chat import (
    ChatEventType,
    ChatMessage,
    ChatRole,
    ChatRun,
    ChatRunStatus,
    ChatSession,
)

NOW = datetime(2026, 6, 27, 8, 0, tzinfo=UTC)


def test_chat_session_requires_non_empty_title() -> None:
    with pytest.raises(ValidationError):
        ChatSession(title=" ")


def test_chat_message_round_trip_model() -> None:
    message = ChatMessage(
        id="11111111-1111-4111-8111-111111111111",
        session_id="22222222-2222-4222-8222-222222222222",
        role=ChatRole.USER,
        content="为什么K线不更新",
        created_at=NOW,
    )

    assert message.role is ChatRole.USER
    assert message.inspection_id is None


def test_chat_run_failed_requires_error_code_and_message() -> None:
    with pytest.raises(ValidationError):
        ChatRun(
            session_id="22222222-2222-4222-8222-222222222222",
            user_message_id="11111111-1111-4111-8111-111111111111",
            status=ChatRunStatus.FAILED,
            created_at=NOW,
            finished_at=NOW,
        )


def test_chat_run_failed_requires_non_blank_error_code_and_message() -> None:
    with pytest.raises(ValidationError):
        ChatRun(
            session_id="22222222-2222-4222-8222-222222222222",
            user_message_id="11111111-1111-4111-8111-111111111111",
            status=ChatRunStatus.FAILED,
            error_code=" ",
            error_message=" ",
            created_at=NOW,
            finished_at=NOW,
        )


def test_chat_run_non_failed_rejects_error_code_and_message() -> None:
    with pytest.raises(ValidationError):
        ChatRun(
            session_id="22222222-2222-4222-8222-222222222222",
            user_message_id="11111111-1111-4111-8111-111111111111",
            status=ChatRunStatus.COMPLETED,
            error_code="chat.failed",
            error_message="聊天任务失败",
            created_at=NOW,
            finished_at=NOW,
        )


def test_chat_run_event_uses_stable_event_type() -> None:
    event = ChatRun.Event(
        run_id="33333333-3333-4333-8333-333333333333",
        event_type=ChatEventType.ACCEPTED,
        payload={"question": "为什么K线不更新"},
        created_at=NOW,
    )

    assert event.event_type is ChatEventType.ACCEPTED
