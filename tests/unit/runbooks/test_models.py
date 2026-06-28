from datetime import UTC, datetime, timedelta

import pytest

from datasentry.domain import OperationRisk
from datasentry.runbooks import (
    ExecutionMode,
    OperationEvent,
    OperationEventType,
    OperationLock,
    Runbook,
    RunbookExecutionResult,
    RunbookVerificationResult,
)


def test_runbook_requires_mock_execution_for_enabled_low_risk_runbook() -> None:
    runbook = Runbook(
        name="mock.restart_preview",
        version="1.0.0",
        title="模拟重启",
        description="仅用于本地演练",
        risk=OperationRisk.L1,
        execution_mode=ExecutionMode.MOCK,
        parameter_schema={"type": "object", "required": ["target"]},
        precheck={"summary": "检查目标"},
        postcheck={"summary": "验证目标"},
        lock_key_template="runbook:{name}:{target}",
        idempotency_key_template="{name}:{version}:{target}:{incident_id}",
    )

    assert runbook.name == "mock.restart_preview"


def test_enabled_runbook_rejects_unknown_execution_mode() -> None:
    with pytest.raises(ValueError, match=r"mock|forbidden"):
        Runbook(
            name="unsafe.shell",
            version="1.0.0",
            title="危险命令",
            description="不允许执行",
            risk=OperationRisk.L1,
            execution_mode="shell",
            parameter_schema={"type": "object"},
            precheck={},
            postcheck={},
            lock_key_template="{name}",
            idempotency_key_template="{name}",
        )


def test_operation_event_payload_is_redacted() -> None:
    event = OperationEvent(
        operation_id="operation-1",
        event_type=OperationEventType.OPERATION_REQUESTED,
        summary="创建操作",
        actor="operator",
        payload={"Authorization": "Bearer secret-token", "target": "api"},
    )

    assert event.payload["Authorization"] == "[REDACTED]"
    assert event.payload["target"] == "api"


def test_operation_lock_requires_expiry_after_acquire_time() -> None:
    acquired_at = datetime(2026, 6, 28, 10, 0, tzinfo=UTC)

    with pytest.raises(ValueError, match="锁过期时间必须晚于获取时间"):
        OperationLock(
            lock_key="runbook:api",
            operation_id="operation-1",
            runbook_name="mock.restart_preview",
            target="api",
            acquired_at=acquired_at,
            expires_at=acquired_at - timedelta(seconds=1),
        )


def test_runbook_execution_result_requires_explicit_timestamps() -> None:
    with pytest.raises(ValueError):
        RunbookExecutionResult(
            status="succeeded",
            summary="执行完成",
        )


def test_runbook_execution_result_rejects_finished_before_started() -> None:
    started_at = datetime(2026, 6, 28, 10, 0, tzinfo=UTC)

    with pytest.raises(ValueError, match="执行结束时间不能早于开始时间"):
        RunbookExecutionResult(
            status="failed",
            summary="执行失败",
            started_at=started_at,
            finished_at=started_at - timedelta(seconds=1),
        )


def test_runbook_verification_result_uses_verified_at() -> None:
    verified_at = datetime(2026, 6, 28, 10, 0, tzinfo=UTC)

    result = RunbookVerificationResult(
        status="succeeded",
        summary="验证通过",
        verified_at=verified_at,
    )

    assert result.verified_at == verified_at
    assert not hasattr(result, "started_at")
    assert not hasattr(result, "finished_at")


def test_runbook_verification_result_requires_timezone_aware_verified_at() -> None:
    with pytest.raises(ValueError, match="datetime 必须包含时区信息"):
        RunbookVerificationResult(
            status="failed",
            summary="验证失败",
            verified_at=datetime(2026, 6, 28, 10, 0),
        )
