from datetime import UTC, datetime, timedelta

import pytest

from datasentry.domain import OperationRisk
from datasentry.runbooks import (
    ExecutionMode,
    OperationEvent,
    OperationEventType,
    OperationLock,
    Runbook,
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
