"""有限自治策略评估。"""

from collections.abc import Callable
from datetime import datetime

from pydantic import JsonValue

from datasentry.autonomy.models import (
    AutonomyDecision,
    AutonomyDecisionStatus,
    AutonomyPolicy,
    CircuitBreakerState,
)
from datasentry.domain.common import utc_now
from datasentry.runbooks import ExecutionMode, Runbook


class AutonomyPolicyEngine:
    """用确定性策略判断候选 Runbook 是否允许自治执行。"""

    def __init__(self, *, clock: Callable[[], datetime] = utc_now) -> None:
        self._clock = clock

    def evaluate(
        self,
        *,
        policy: AutonomyPolicy,
        runbook: Runbook,
        parameters: dict[str, JsonValue],
        incident_id: str | None,
    ) -> AutonomyDecision:
        target = _target(parameters)
        if not policy.enabled:
            return _decision(
                AutonomyDecisionStatus.BLOCKED,
                "policy.disabled",
                "自治策略未启用",
                runbook,
                target,
                incident_id,
            )
        if runbook.execution_mode is not ExecutionMode.MOCK:
            return _decision(
                AutonomyDecisionStatus.BLOCKED,
                "policy.execution_mode_not_allowed",
                "自治只允许 mock 执行模式",
                runbook,
                target,
                incident_id,
            )
        if runbook.risk not in policy.allowed_risks:
            return _decision(
                AutonomyDecisionStatus.BLOCKED,
                "policy.risk_not_allowed",
                "Runbook 风险等级不允许自治执行",
                runbook,
                target,
                incident_id,
            )
        if policy.circuit_breaker_state is CircuitBreakerState.OPEN:
            return _decision(
                AutonomyDecisionStatus.BLOCKED,
                "policy.circuit_open",
                "自治熔断器已打开",
                runbook,
                target,
                incident_id,
            )

        now = self._clock()
        window_matched = any(window.matches(now) for window in policy.maintenance_windows)
        if not window_matched and not policy.shadow_mode:
            return _decision(
                AutonomyDecisionStatus.ESCALATED,
                "policy.maintenance_window_missed",
                "当前时间不在自治维护窗口内",
                runbook,
                target,
                incident_id,
                window_matched=False,
            )

        if policy.shadow_mode:
            return _decision(
                AutonomyDecisionStatus.SHADOWED,
                "policy.shadow_mode",
                "自治策略处于 shadow 模式，仅记录不执行",
                runbook,
                target,
                incident_id,
                window_matched=window_matched,
            )

        return _decision(
            AutonomyDecisionStatus.ALLOWED,
            "policy.allowed",
            "自治策略允许 mock 自动执行",
            runbook,
            target,
            incident_id,
            window_matched=True,
        )


def _target(parameters: dict[str, JsonValue]) -> str | None:
    value = parameters.get("target")
    if isinstance(value, str) and value.strip():
        return value
    return None


def _decision(
    status: AutonomyDecisionStatus,
    reason_code: str,
    reason: str,
    runbook: Runbook,
    target: str | None,
    incident_id: str | None,
    *,
    window_matched: bool = False,
) -> AutonomyDecision:
    return AutonomyDecision(
        status=status,
        reason_code=reason_code,
        reason=reason,
        runbook_name=runbook.name,
        target=target,
        incident_id=incident_id,
        window_matched=window_matched,
        payload={
            "risk": runbook.risk.value,
            "execution_mode": runbook.execution_mode.value,
        },
    )
