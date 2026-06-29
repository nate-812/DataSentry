from datetime import UTC, datetime

from datasentry.autonomy import (
    AutonomyDecisionStatus,
    AutonomyPolicy,
    CircuitBreakerState,
    MaintenanceWindow,
)
from datasentry.autonomy.policy import AutonomyPolicyEngine
from datasentry.domain import OperationRisk
from datasentry.runbooks import BuiltInRunbookCatalog


NOW = datetime(2026, 6, 29, 2, 0, tzinfo=UTC)


def _runbook(name: str = "mock.restart_preview"):
    return BuiltInRunbookCatalog().get(name)


def test_disabled_policy_blocks_candidate() -> None:
    decision = AutonomyPolicyEngine(clock=lambda: NOW).evaluate(
        policy=AutonomyPolicy(runbook_name="mock.restart_preview", enabled=False),
        runbook=_runbook(),
        parameters={"target": "api", "reason": "演练"},
        incident_id=None,
    )

    assert decision.status is AutonomyDecisionStatus.BLOCKED
    assert decision.reason_code == "policy.disabled"


def test_enabled_shadow_policy_records_shadow_decision() -> None:
    decision = AutonomyPolicyEngine(clock=lambda: NOW).evaluate(
        policy=AutonomyPolicy(
            runbook_name="mock.restart_preview",
            enabled=True,
            shadow_mode=True,
        ),
        runbook=_runbook(),
        parameters={"target": "api", "reason": "演练"},
        incident_id="incident-1",
    )

    assert decision.status is AutonomyDecisionStatus.SHADOWED
    assert decision.reason_code == "policy.shadow_mode"
    assert decision.target == "api"
    assert decision.incident_id == "incident-1"


def test_enabled_non_shadow_policy_allows_mock_l1_inside_window() -> None:
    decision = AutonomyPolicyEngine(clock=lambda: NOW).evaluate(
        policy=AutonomyPolicy(
            runbook_name="mock.restart_preview",
            enabled=True,
            shadow_mode=False,
        ),
        runbook=_runbook(),
        parameters={"target": "api", "reason": "演练"},
        incident_id=None,
    )

    assert decision.status is AutonomyDecisionStatus.ALLOWED
    assert decision.reason_code == "policy.allowed"


def test_policy_escalates_outside_maintenance_window() -> None:
    decision = AutonomyPolicyEngine(clock=lambda: NOW).evaluate(
        policy=AutonomyPolicy(
            runbook_name="mock.restart_preview",
            enabled=True,
            shadow_mode=False,
            maintenance_windows=[
                MaintenanceWindow(
                    weekdays=[0],
                    start_minute_utc=700,
                    end_minute_utc=800,
                ),
            ],
        ),
        runbook=_runbook(),
        parameters={"target": "api", "reason": "演练"},
        incident_id=None,
    )

    assert decision.status is AutonomyDecisionStatus.ESCALATED
    assert decision.reason_code == "policy.maintenance_window_missed"


def test_policy_blocks_open_circuit_breaker() -> None:
    decision = AutonomyPolicyEngine(clock=lambda: NOW).evaluate(
        policy=AutonomyPolicy(
            runbook_name="mock.restart_preview",
            enabled=True,
            shadow_mode=False,
            circuit_breaker_state=CircuitBreakerState.OPEN,
        ),
        runbook=_runbook(),
        parameters={"target": "api", "reason": "演练"},
        incident_id=None,
    )

    assert decision.status is AutonomyDecisionStatus.BLOCKED
    assert decision.reason_code == "policy.circuit_open"


def test_policy_blocks_risk_outside_allowed_set() -> None:
    runbook = _runbook().model_copy(update={"risk": OperationRisk.L2})
    decision = AutonomyPolicyEngine(clock=lambda: NOW).evaluate(
        policy=AutonomyPolicy(runbook_name="mock.restart_preview", enabled=True),
        runbook=runbook,
        parameters={"target": "api", "reason": "演练"},
        incident_id=None,
    )

    assert decision.status is AutonomyDecisionStatus.BLOCKED
    assert decision.reason_code == "policy.risk_not_allowed"
