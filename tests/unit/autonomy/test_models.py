from datetime import UTC, datetime

import pytest

from datasentry.autonomy import (
    AutonomyDecision,
    AutonomyDecisionStatus,
    AutonomyPolicy,
    AutonomyRunRecord,
    CircuitBreakerState,
    MaintenanceWindow,
    RateLimitRule,
)
from datasentry.domain import OperationRisk


def test_maintenance_window_matches_utc_minute_range() -> None:
    window = MaintenanceWindow(
        weekdays=[0, 1, 2, 3, 4],
        start_minute_utc=60,
        end_minute_utc=600,
    )

    assert window.matches(datetime(2026, 6, 29, 2, 0, tzinfo=UTC)) is True
    assert window.matches(datetime(2026, 6, 29, 11, 0, tzinfo=UTC)) is False
    assert window.matches(datetime(2026, 7, 4, 2, 0, tzinfo=UTC)) is False


def test_maintenance_window_rejects_invalid_range() -> None:
    with pytest.raises(ValueError, match="维护窗口结束分钟必须大于开始分钟"):
        MaintenanceWindow(weekdays=[0], start_minute_utc=600, end_minute_utc=60)


def test_policy_defaults_to_disabled_shadow_mode() -> None:
    policy = AutonomyPolicy(runbook_name="mock.restart_preview")

    assert policy.enabled is False
    assert policy.shadow_mode is True
    assert policy.allowed_risks == [OperationRisk.L0, OperationRisk.L1]
    assert policy.circuit_breaker_state is CircuitBreakerState.CLOSED


def test_rate_limit_rule_rejects_non_positive_limit() -> None:
    with pytest.raises(ValueError, match="速率限制次数必须大于 0"):
        RateLimitRule(scope="per_runbook", window_seconds=300, limit=0)


def test_decision_payload_is_redacted() -> None:
    decision = AutonomyDecision(
        status=AutonomyDecisionStatus.BLOCKED,
        reason_code="policy.disabled",
        reason="自治策略未启用",
        runbook_name="mock.restart_preview",
        payload={"Authorization": "Bearer secret-token", "target": "api"},
    )

    assert decision.payload["Authorization"] == "[REDACTED]"
    assert decision.payload["target"] == "api"


def test_run_record_requires_operation_for_allowed_decision() -> None:
    with pytest.raises(ValueError, match="allowed 决策必须关联 Operation"):
        AutonomyRunRecord(
            runbook_name="mock.restart_preview",
            target="api",
            decision_status=AutonomyDecisionStatus.ALLOWED,
            reason_code="policy.allowed",
            reason="允许自动执行",
        )
