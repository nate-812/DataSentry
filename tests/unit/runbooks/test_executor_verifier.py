from datetime import UTC, datetime

from datasentry.domain import Operation, OperationRisk, OperationStatus
from datasentry.runbooks import BuiltInRunbookCatalog, MockOperationVerifier, MockRunbookExecutor


def test_mock_executor_returns_deterministic_success() -> None:
    runbook = BuiltInRunbookCatalog().get("mock.restart_preview")
    operation = Operation(
        name=runbook.name,
        version=runbook.version,
        parameters={"target": "api", "reason": "演练"},
        risk=OperationRisk.L1,
        status=OperationStatus.RUNNING,
        requester="operator",
    )

    result = MockRunbookExecutor(clock=lambda: datetime(2026, 6, 28, 10, 0, tzinfo=UTC)).execute(
        runbook,
        operation,
    )

    assert result.status == "succeeded"
    assert result.details["target"] == "api"
    assert "模拟" in result.summary


def test_mock_verifier_returns_independent_success() -> None:
    runbook = BuiltInRunbookCatalog().get("mock.restart_preview")
    operation = Operation(
        name=runbook.name,
        version=runbook.version,
        parameters={"target": "api", "reason": "演练"},
        risk=OperationRisk.L1,
        requester="operator",
    )

    result = MockOperationVerifier(clock=lambda: datetime(2026, 6, 28, 10, 1, tzinfo=UTC)).verify(
        runbook,
        operation,
    )

    assert result.status == "succeeded"
    assert result.details["verification_source"] == "mock_postcheck"


def test_mock_verifier_includes_postcheck_summary() -> None:
    runbook = (
        BuiltInRunbookCatalog()
        .get("mock.restart_preview")
        .model_copy(update={"postcheck": {"summary": "确认 API 状态恢复"}})
    )
    operation = Operation(
        name=runbook.name,
        version=runbook.version,
        parameters={"target": "api", "reason": "演练"},
        risk=OperationRisk.L1,
        requester="operator",
    )

    result = MockOperationVerifier(clock=lambda: datetime(2026, 6, 28, 10, 1, tzinfo=UTC)).verify(
        runbook,
        operation,
    )

    assert "确认 API 状态恢复" in result.summary
    assert result.details["postcheck_summary"] == "确认 API 状态恢复"
