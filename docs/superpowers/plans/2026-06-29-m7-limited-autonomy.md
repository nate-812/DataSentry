# M7 Limited Autonomy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first M7 limited-autonomy control layer for mock Runbooks with deterministic policy evaluation, shadow mode, rate limits, circuit breakers, auditable run records, API access, and console visibility.

**Architecture:** Add a focused `datasentry.autonomy` package that sits in front of the existing M6 `RunbookOperationService`. The autonomy service evaluates candidates against local policies and only calls the M6 request/approve/execute path when the decision is `allowed`; shadow, blocked, and escalated decisions are recorded without executing. SQLite stores policies, run records, rate counters, and circuit breaker state, while FastAPI and React expose the local control surface.

**Tech Stack:** Python 3.12, Pydantic v2, SQLite migrations, FastAPI, pytest, React, TypeScript, Vite, lucide-react.

---

## File Structure

- Create `src/datasentry/autonomy/models.py`: autonomy policy, maintenance window, rate limit, decision, run record, stats, and circuit breaker models.
- Create `src/datasentry/autonomy/policy.py`: deterministic policy engine and reason codes.
- Create `src/datasentry/autonomy/service.py`: evaluate and execute orchestration that delegates allowed mock execution to `RunbookOperationService`.
- Create `src/datasentry/autonomy/catalog.py`: built-in default policies for M6 mock Runbooks.
- Create `src/datasentry/autonomy/__init__.py`: package exports.
- Create `src/datasentry/storage/sql/0006_limited_autonomy.sql`: M7 schema migration.
- Modify `src/datasentry/storage/repository.py`: add autonomy policy, run, counter, stats, and circuit breaker protocol methods.
- Modify `src/datasentry/storage/sqlite.py`: implement M7 persistence methods.
- Modify `src/datasentry/api/schemas.py`: add autonomy request and response schemas.
- Create `src/datasentry/api/routes/autonomy.py`: policy, evaluate, execute, run, stats, and circuit breaker routes.
- Modify `src/datasentry/api/dependencies.py`: provide `AutonomyService` and default policy catalog.
- Modify `src/datasentry/api/app.py`: include autonomy router.
- Modify `frontend/src/api/types.ts`: add autonomy policy, decision, run, stats, and circuit breaker types.
- Modify `frontend/src/api/client.ts`: add autonomy API client methods.
- Modify `frontend/src/pages/ApprovalsPage.tsx`: add the autonomy panel to the existing Runbook approval console.
- Modify `frontend/src/styles/app.css`: add compact autonomy table, status, and segmented control styles.
- Modify `README.md`: document M7 local shadow and mock-autonomy usage.
- Modify `docs/PROJECT_STATUS.md`: record M7 implementation progress and cloud boundary.

---

## Task 1: Autonomy Domain Models And Built-In Policies

**Files:**
- Create: `src/datasentry/autonomy/models.py`
- Create: `src/datasentry/autonomy/catalog.py`
- Create: `src/datasentry/autonomy/__init__.py`
- Test: `tests/unit/autonomy/test_models.py`
- Test: `tests/unit/autonomy/test_catalog.py`

- [ ] **Step 1: Write failing model tests**

Add `tests/unit/autonomy/test_models.py`:

```python
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
        payload={"Authorization": "Bearer secret-token"},
    )

    assert decision.payload["Authorization"] == "[REDACTED]"


def test_run_record_requires_operation_for_allowed_decision() -> None:
    with pytest.raises(ValueError, match="allowed 决策必须关联 Operation"):
        AutonomyRunRecord(
            runbook_name="mock.restart_preview",
            target="api",
            decision_status=AutonomyDecisionStatus.ALLOWED,
            reason_code="policy.allowed",
            reason="允许自动执行",
        )
```

- [ ] **Step 2: Write failing catalog tests**

Add `tests/unit/autonomy/test_catalog.py`:

```python
from datasentry.autonomy import BuiltInAutonomyPolicyCatalog


def test_builtin_policy_catalog_defaults_to_disabled_shadow_policies() -> None:
    catalog = BuiltInAutonomyPolicyCatalog()

    policies = catalog.list_policies()

    assert [policy.runbook_name for policy in policies] == [
        "mock.restart_preview",
        "mock.clear_cache_preview",
    ]
    assert all(policy.enabled is False for policy in policies)
    assert all(policy.shadow_mode is True for policy in policies)


def test_builtin_policy_catalog_returns_copy() -> None:
    catalog = BuiltInAutonomyPolicyCatalog()

    policy = catalog.get("mock.restart_preview")
    policy.enabled = True

    assert catalog.get("mock.restart_preview").enabled is False
```

- [ ] **Step 3: Run tests to verify RED**

Run:

```bash
.venv/bin/pytest tests/unit/autonomy/test_models.py tests/unit/autonomy/test_catalog.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'datasentry.autonomy'`.

- [ ] **Step 4: Implement models and catalog**

Create `src/datasentry/autonomy/models.py`:

```python
"""M7 有限自治领域模型。"""

from datetime import datetime
from enum import StrEnum
from typing import Self, cast

from pydantic import Field, JsonValue, field_validator, model_validator

from datasentry.domain.common import DomainModel, new_id, require_aware_datetime, utc_now
from datasentry.domain.enums import OperationRisk
from datasentry.redaction import redact_value


class CircuitBreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class AutonomyDecisionStatus(StrEnum):
    ALLOWED = "allowed"
    SHADOWED = "shadowed"
    BLOCKED = "blocked"
    ESCALATED = "escalated"


class MaintenanceWindow(DomainModel):
    weekdays: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])
    start_minute_utc: int = Field(default=60, ge=0, le=1439)
    end_minute_utc: int = Field(default=600, ge=1, le=1440)

    @field_validator("weekdays")
    @classmethod
    def validate_weekdays(cls, value: list[int]) -> list[int]:
        unique_weekdays = sorted(set(value))
        if not unique_weekdays:
            raise ValueError("维护窗口必须至少包含一天")
        if any(weekday < 0 or weekday > 6 for weekday in unique_weekdays):
            raise ValueError("维护窗口星期必须在 0 到 6 之间")
        return unique_weekdays

    @model_validator(mode="after")
    def validate_window_range(self) -> Self:
        if self.end_minute_utc <= self.start_minute_utc:
            raise ValueError("维护窗口结束分钟必须大于开始分钟")
        return self

    def matches(self, now: datetime) -> bool:
        require_aware_datetime(now)
        minute_of_day = now.hour * 60 + now.minute
        return now.weekday() in self.weekdays and (
            self.start_minute_utc <= minute_of_day < self.end_minute_utc
        )


class RateLimitRule(DomainModel):
    scope: str = Field(pattern=r"^(per_runbook|per_target|per_incident)$")
    window_seconds: int = Field(default=3600, gt=0)
    limit: int = Field(default=3, gt=0)

    @field_validator("limit")
    @classmethod
    def validate_limit(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("速率限制次数必须大于 0")
        return value


class AutonomyPolicy(DomainModel):
    runbook_name: str = Field(min_length=1)
    enabled: bool = False
    shadow_mode: bool = True
    allowed_risks: list[OperationRisk] = Field(
        default_factory=lambda: [OperationRisk.L0, OperationRisk.L1],
    )
    maintenance_windows: list[MaintenanceWindow] = Field(
        default_factory=lambda: [MaintenanceWindow()],
    )
    rate_limits: list[RateLimitRule] = Field(
        default_factory=lambda: [
            RateLimitRule(scope="per_runbook", window_seconds=3600, limit=3),
            RateLimitRule(scope="per_target", window_seconds=3600, limit=1),
            RateLimitRule(scope="per_incident", window_seconds=3600, limit=1),
        ],
    )
    min_success_rate: float = Field(default=0.95, ge=0, le=1)
    min_success_samples: int = Field(default=5, ge=0)
    failure_threshold: int = Field(default=2, gt=0)
    circuit_breaker_state: CircuitBreakerState = CircuitBreakerState.CLOSED
    updated_at: datetime = Field(default_factory=utc_now)

    _normalize_updated_at = field_validator("updated_at")(require_aware_datetime)


class AutonomyDecision(DomainModel):
    status: AutonomyDecisionStatus
    reason_code: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    runbook_name: str = Field(min_length=1)
    target: str | None = None
    incident_id: str | None = None
    operation_id: str | None = None
    window_matched: bool = False
    payload: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("payload")
    @classmethod
    def redact_payload(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return cast("dict[str, JsonValue]", redact_value(value))


class AutonomyRunRecord(DomainModel):
    id: str = Field(default_factory=new_id)
    runbook_name: str = Field(min_length=1)
    target: str = Field(min_length=1)
    incident_id: str | None = None
    operation_id: str | None = None
    decision_status: AutonomyDecisionStatus
    reason_code: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None
    succeeded: bool | None = None
    payload: dict[str, JsonValue] = Field(default_factory=dict)

    _normalize_created_at = field_validator("created_at")(require_aware_datetime)

    @field_validator("payload")
    @classmethod
    def redact_payload(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return cast("dict[str, JsonValue]", redact_value(value))

    @model_validator(mode="after")
    def validate_allowed_operation_link(self) -> Self:
        if (
            self.decision_status is AutonomyDecisionStatus.ALLOWED
            and self.operation_id is None
        ):
            raise ValueError("allowed 决策必须关联 Operation")
        return self
```

Create `src/datasentry/autonomy/catalog.py`:

```python
"""内置有限自治策略目录。"""

from datasentry.autonomy.models import AutonomyPolicy
from datasentry.errors import NotFoundError


class BuiltInAutonomyPolicyCatalog:
    def __init__(self) -> None:
        self._policies = {
            "mock.restart_preview": AutonomyPolicy(runbook_name="mock.restart_preview"),
            "mock.clear_cache_preview": AutonomyPolicy(runbook_name="mock.clear_cache_preview"),
        }

    def list_policies(self) -> list[AutonomyPolicy]:
        return [policy.model_copy(deep=True) for policy in self._policies.values()]

    def get(self, runbook_name: str) -> AutonomyPolicy:
        policy = self._policies.get(runbook_name)
        if policy is None:
            raise NotFoundError("未找到指定自治策略", details={"runbook_name": runbook_name})
        return policy.model_copy(deep=True)
```

Create `src/datasentry/autonomy/__init__.py`:

```python
"""M7 有限自治控制层。"""

from datasentry.autonomy.catalog import BuiltInAutonomyPolicyCatalog
from datasentry.autonomy.models import (
    AutonomyDecision,
    AutonomyDecisionStatus,
    AutonomyPolicy,
    AutonomyRunRecord,
    CircuitBreakerState,
    MaintenanceWindow,
    RateLimitRule,
)

__all__ = [
    "AutonomyDecision",
    "AutonomyDecisionStatus",
    "AutonomyPolicy",
    "AutonomyRunRecord",
    "BuiltInAutonomyPolicyCatalog",
    "CircuitBreakerState",
    "MaintenanceWindow",
    "RateLimitRule",
]
```

- [ ] **Step 5: Run tests to verify GREEN**

Run:

```bash
.venv/bin/pytest tests/unit/autonomy/test_models.py tests/unit/autonomy/test_catalog.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/datasentry/autonomy tests/unit/autonomy/test_models.py tests/unit/autonomy/test_catalog.py
git commit -m "feat: 增加M7自治领域模型"
```

---

## Task 2: Policy Engine With Shadow, Windows, Risk, And Circuit Breakers

**Files:**
- Create: `src/datasentry/autonomy/policy.py`
- Test: `tests/unit/autonomy/test_policy.py`

- [ ] **Step 1: Write failing policy tests**

Add `tests/unit/autonomy/test_policy.py`:

```python
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
        policy=AutonomyPolicy(runbook_name="mock.restart_preview", enabled=True, shadow_mode=True),
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
        policy=AutonomyPolicy(runbook_name="mock.restart_preview", enabled=True, shadow_mode=False),
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
                MaintenanceWindow(weekdays=[0], start_minute_utc=700, end_minute_utc=800),
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
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
.venv/bin/pytest tests/unit/autonomy/test_policy.py -q
```

Expected: FAIL with `ModuleNotFoundError` for `datasentry.autonomy.policy`.

- [ ] **Step 3: Implement policy engine**

Create `src/datasentry/autonomy/policy.py`:

```python
"""有限自治策略评估。"""

from collections.abc import Callable

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
    def __init__(self, *, clock: Callable = utc_now) -> None:
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
            return _decision("blocked", "policy.disabled", "自治策略未启用", runbook, target, incident_id)
        if runbook.execution_mode is not ExecutionMode.MOCK:
            return _decision("blocked", "policy.execution_mode_not_allowed", "自治只允许 mock 执行模式", runbook, target, incident_id)
        if runbook.risk not in policy.allowed_risks:
            return _decision("blocked", "policy.risk_not_allowed", "Runbook 风险等级不允许自治执行", runbook, target, incident_id)
        if policy.circuit_breaker_state is CircuitBreakerState.OPEN:
            return _decision("blocked", "policy.circuit_open", "自治熔断器已打开", runbook, target, incident_id)

        now = self._clock()
        window_matched = any(window.matches(now) for window in policy.maintenance_windows)
        if not window_matched and not policy.shadow_mode:
            decision = _decision("escalated", "policy.maintenance_window_missed", "当前时间不在自治维护窗口内", runbook, target, incident_id)
            decision.window_matched = False
            return decision

        if policy.shadow_mode:
            decision = _decision("shadowed", "policy.shadow_mode", "自治策略处于 shadow 模式，仅记录不执行", runbook, target, incident_id)
            decision.window_matched = window_matched
            return decision

        decision = _decision("allowed", "policy.allowed", "自治策略允许 mock 自动执行", runbook, target, incident_id)
        decision.window_matched = True
        return decision


def _target(parameters: dict[str, JsonValue]) -> str | None:
    value = parameters.get("target")
    return value if isinstance(value, str) and value.strip() else None


def _decision(
    status: str,
    reason_code: str,
    reason: str,
    runbook: Runbook,
    target: str | None,
    incident_id: str | None,
) -> AutonomyDecision:
    return AutonomyDecision(
        status=AutonomyDecisionStatus(status),
        reason_code=reason_code,
        reason=reason,
        runbook_name=runbook.name,
        target=target,
        incident_id=incident_id,
        payload={"risk": runbook.risk.value, "execution_mode": runbook.execution_mode.value},
    )
```

Update `src/datasentry/autonomy/__init__.py` to export `AutonomyPolicyEngine`.

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
.venv/bin/pytest tests/unit/autonomy/test_policy.py tests/unit/autonomy/test_models.py tests/unit/autonomy/test_catalog.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/datasentry/autonomy tests/unit/autonomy/test_policy.py
git commit -m "feat: 增加M7自治策略评估"
```

---

## Task 3: SQLite Persistence For Autonomy Policies And Runs

**Files:**
- Create: `src/datasentry/storage/sql/0006_limited_autonomy.sql`
- Modify: `src/datasentry/storage/repository.py`
- Modify: `src/datasentry/storage/sqlite.py`
- Test: `tests/integration/storage/test_sqlite_autonomy.py`
- Test: `tests/integration/storage/test_migrations.py`

- [ ] **Step 1: Write failing storage tests**

Add `tests/integration/storage/test_sqlite_autonomy.py`:

```python
from datetime import UTC, datetime

from datasentry.autonomy import (
    AutonomyDecisionStatus,
    AutonomyPolicy,
    AutonomyRunRecord,
    CircuitBreakerState,
)
from datasentry.storage import SQLiteRepository, migrate


def _repository(tmp_path):
    database_path = tmp_path / "datasentry.db"
    migrate(database_path)
    return SQLiteRepository(database_path)


def test_repository_saves_and_loads_autonomy_policy(tmp_path) -> None:
    repository = _repository(tmp_path)
    policy = AutonomyPolicy(
        runbook_name="mock.restart_preview",
        enabled=True,
        shadow_mode=False,
        circuit_breaker_state=CircuitBreakerState.HALF_OPEN,
    )

    repository.save_autonomy_policy(policy)
    loaded = repository.get_autonomy_policy("mock.restart_preview")

    assert loaded.runbook_name == "mock.restart_preview"
    assert loaded.enabled is True
    assert loaded.shadow_mode is False
    assert loaded.circuit_breaker_state is CircuitBreakerState.HALF_OPEN


def test_repository_records_autonomy_run_and_lists_recent_runs(tmp_path) -> None:
    repository = _repository(tmp_path)
    record = AutonomyRunRecord(
        runbook_name="mock.restart_preview",
        target="api",
        decision_status=AutonomyDecisionStatus.SHADOWED,
        reason_code="policy.shadow_mode",
        reason="自治策略处于 shadow 模式，仅记录不执行",
        created_at=datetime(2026, 6, 29, 2, 0, tzinfo=UTC),
    )

    repository.save_autonomy_run(record)
    runs = repository.list_autonomy_runs(limit=10)

    assert len(runs) == 1
    assert runs[0].id == record.id
    assert runs[0].decision_status is AutonomyDecisionStatus.SHADOWED


def test_repository_updates_autonomy_run_result(tmp_path) -> None:
    repository = _repository(tmp_path)
    record = AutonomyRunRecord(
        runbook_name="mock.restart_preview",
        target="api",
        operation_id="operation-1",
        decision_status=AutonomyDecisionStatus.ALLOWED,
        reason_code="policy.allowed",
        reason="自治策略允许 mock 自动执行",
    )
    repository.save_autonomy_run(record)

    finished = record.model_copy(
        update={
            "finished_at": datetime(2026, 6, 29, 2, 1, tzinfo=UTC),
            "succeeded": True,
        },
    )
    repository.update_autonomy_run(finished)

    assert repository.list_autonomy_runs(limit=1)[0].succeeded is True
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
.venv/bin/pytest tests/integration/storage/test_sqlite_autonomy.py -q
```

Expected: FAIL because migration and repository methods are missing.

- [ ] **Step 3: Add migration**

Create `src/datasentry/storage/sql/0006_limited_autonomy.sql`:

```sql
CREATE TABLE IF NOT EXISTS autonomy_policies (
    runbook_name TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL,
    shadow_mode INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS autonomy_runs (
    id TEXT PRIMARY KEY,
    runbook_name TEXT NOT NULL,
    target TEXT NOT NULL,
    incident_id TEXT,
    operation_id TEXT,
    decision_status TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    finished_at TEXT,
    succeeded INTEGER,
    payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_autonomy_runs_created_at
ON autonomy_runs(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_autonomy_runs_runbook_created_at
ON autonomy_runs(runbook_name, created_at DESC);

CREATE TABLE IF NOT EXISTS autonomy_circuit_breakers (
    runbook_name TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    failure_count INTEGER NOT NULL,
    opened_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS autonomy_rate_counters (
    scope TEXT NOT NULL,
    counter_key TEXT NOT NULL,
    window_started_at TEXT NOT NULL,
    count INTEGER NOT NULL,
    PRIMARY KEY (scope, counter_key, window_started_at)
);
```

- [ ] **Step 4: Extend repository protocol and SQLite implementation**

Add these methods to `src/datasentry/storage/repository.py`:

```python
from datasentry.autonomy import AutonomyPolicy, AutonomyRunRecord

def save_autonomy_policy(self, policy: AutonomyPolicy) -> None: ...
def get_autonomy_policy(self, runbook_name: str) -> AutonomyPolicy: ...
def list_autonomy_policies(self) -> list[AutonomyPolicy]: ...
def save_autonomy_run(self, record: AutonomyRunRecord) -> None: ...
def update_autonomy_run(self, record: AutonomyRunRecord) -> None: ...
def list_autonomy_runs(self, *, limit: int = 20) -> list[AutonomyRunRecord]: ...
def count_recent_allowed_autonomy_runs(self, *, runbook_name: str, target: str | None, incident_id: str | None, since: datetime) -> int: ...
```

Implement matching methods in `src/datasentry/storage/sqlite.py` using existing JSON serialization helpers and `NotFoundError` patterns. Store full model JSON in `payload_json` for policy and run reconstruction, keep indexed columns duplicated for list queries, and implement `count_recent_allowed_autonomy_runs()` with `decision_status = 'allowed'`, `created_at >= since`, and optional target/incident filters.

- [ ] **Step 5: Run storage tests**

Run:

```bash
.venv/bin/pytest tests/integration/storage/test_sqlite_autonomy.py tests/integration/storage/test_migrations.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/datasentry/storage tests/integration/storage/test_sqlite_autonomy.py
git commit -m "feat: 持久化M7自治记录"
```

---

## Task 4: Autonomy Service Evaluate And Mock Execute Flow

**Files:**
- Create: `src/datasentry/autonomy/service.py`
- Modify: `src/datasentry/autonomy/__init__.py`
- Test: `tests/unit/autonomy/test_service.py`

- [ ] **Step 1: Write failing service tests**

Add `tests/unit/autonomy/test_service.py`:

```python
from datetime import UTC, datetime

from datasentry.autonomy import (
    AutonomyDecisionStatus,
    AutonomyPolicy,
    AutonomyRunRecord,
)
from datasentry.autonomy.service import AutonomyService
from datasentry.domain import Operation, OperationRisk, OperationStatus
from datasentry.runbooks import BuiltInRunbookCatalog


NOW = datetime(2026, 6, 29, 2, 0, tzinfo=UTC)


class FakeAutonomyRepository:
    def __init__(self, policy: AutonomyPolicy) -> None:
        self.policy = policy
        self.runs: list[AutonomyRunRecord] = []

    def get_autonomy_policy(self, runbook_name: str) -> AutonomyPolicy:
        return self.policy.model_copy(deep=True)

    def save_autonomy_run(self, record: AutonomyRunRecord) -> None:
        self.runs.append(record.model_copy(deep=True))

    def update_autonomy_run(self, record: AutonomyRunRecord) -> None:
        self.runs[-1] = record.model_copy(deep=True)

    def count_recent_allowed_autonomy_runs(self, *, runbook_name, target, incident_id, since):
        return 0


class FakeRunbookOperationService:
    def __init__(self) -> None:
        self.requested = False
        self.approved = False
        self.executed = False
        self.operation = Operation(
            id="operation-1",
            name="mock.restart_preview",
            version="1.0.0",
            parameters={"target": "api", "reason": "演练"},
            risk=OperationRisk.L1,
            status=OperationStatus.AWAITING_APPROVAL,
            requester="datasentry-autonomy",
            requested_at=NOW,
        )

    def request(self, runbook_name, parameters, requester, incident_id=None):
        self.requested = True
        return self.operation

    def approve(self, operation_id, approver):
        self.approved = True
        self.operation = self.operation.model_copy(update={"status": OperationStatus.APPROVED})
        return self.operation

    def execute(self, operation_id, actor):
        self.executed = True
        self.operation = self.operation.model_copy(update={"status": OperationStatus.SUCCEEDED})
        return self.operation


def test_shadow_decision_records_run_without_operation() -> None:
    repository = FakeAutonomyRepository(
        AutonomyPolicy(runbook_name="mock.restart_preview", enabled=True, shadow_mode=True),
    )
    runbook_service = FakeRunbookOperationService()
    service = AutonomyService(
        repository=repository,
        runbook_catalog=BuiltInRunbookCatalog(),
        runbook_operation_service=runbook_service,
        clock=lambda: NOW,
    )

    decision = service.execute_candidate(
        "mock.restart_preview",
        parameters={"target": "api", "reason": "演练"},
        incident_id=None,
    )

    assert decision.status is AutonomyDecisionStatus.SHADOWED
    assert runbook_service.requested is False
    assert repository.runs[0].decision_status is AutonomyDecisionStatus.SHADOWED


def test_allowed_decision_delegates_to_runbook_service() -> None:
    repository = FakeAutonomyRepository(
        AutonomyPolicy(runbook_name="mock.restart_preview", enabled=True, shadow_mode=False),
    )
    runbook_service = FakeRunbookOperationService()
    service = AutonomyService(
        repository=repository,
        runbook_catalog=BuiltInRunbookCatalog(),
        runbook_operation_service=runbook_service,
        clock=lambda: NOW,
    )

    decision = service.execute_candidate(
        "mock.restart_preview",
        parameters={"target": "api", "reason": "演练"},
        incident_id="incident-1",
    )

    assert decision.status is AutonomyDecisionStatus.ALLOWED
    assert decision.operation_id == "operation-1"
    assert runbook_service.requested is True
    assert runbook_service.approved is True
    assert runbook_service.executed is True
    assert repository.runs[-1].succeeded is True
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
.venv/bin/pytest tests/unit/autonomy/test_service.py -q
```

Expected: FAIL because `AutonomyService` is missing.

- [ ] **Step 3: Implement service**

Create `src/datasentry/autonomy/service.py`:

```python
"""有限自治服务编排。"""

from collections.abc import Callable
from typing import Protocol

from pydantic import JsonValue

from datasentry.autonomy.models import (
    AutonomyDecision,
    AutonomyDecisionStatus,
    AutonomyPolicy,
    AutonomyRunRecord,
)
from datasentry.autonomy.policy import AutonomyPolicyEngine
from datasentry.domain import OperationStatus
from datasentry.domain.common import utc_now
from datasentry.runbooks import Runbook, RunbookOperationService


class AutonomyRepository(Protocol):
    def get_autonomy_policy(self, runbook_name: str) -> AutonomyPolicy:
        raise NotImplementedError  # pragma: no cover

    def save_autonomy_run(self, record: AutonomyRunRecord) -> None:
        raise NotImplementedError  # pragma: no cover

    def update_autonomy_run(self, record: AutonomyRunRecord) -> None:
        raise NotImplementedError  # pragma: no cover


class RunbookCatalog(Protocol):
    def get(self, name: str) -> Runbook:
        raise NotImplementedError  # pragma: no cover


class AutonomyService:
    def __init__(
        self,
        *,
        repository: AutonomyRepository,
        runbook_catalog: RunbookCatalog,
        runbook_operation_service: RunbookOperationService,
        policy_engine: AutonomyPolicyEngine | None = None,
        clock: Callable = utc_now,
    ) -> None:
        self._repository = repository
        self._runbook_catalog = runbook_catalog
        self._runbook_operation_service = runbook_operation_service
        self._policy_engine = policy_engine or AutonomyPolicyEngine(clock=clock)
        self._clock = clock

    def evaluate_candidate(
        self,
        runbook_name: str,
        *,
        parameters: dict[str, JsonValue],
        incident_id: str | None,
    ) -> AutonomyDecision:
        policy = self._repository.get_autonomy_policy(runbook_name)
        runbook = self._runbook_catalog.get(runbook_name)
        return self._policy_engine.evaluate(
            policy=policy,
            runbook=runbook,
            parameters=parameters,
            incident_id=incident_id,
        )

    def execute_candidate(
        self,
        runbook_name: str,
        *,
        parameters: dict[str, JsonValue],
        incident_id: str | None,
    ) -> AutonomyDecision:
        decision = self.evaluate_candidate(
            runbook_name,
            parameters=parameters,
            incident_id=incident_id,
        )
        target = decision.target or "unknown"
        record = AutonomyRunRecord(
            runbook_name=decision.runbook_name,
            target=target,
            incident_id=decision.incident_id,
            decision_status=decision.status,
            reason_code=decision.reason_code,
            reason=decision.reason,
            created_at=self._clock(),
            payload=decision.payload,
        )

        if decision.status is not AutonomyDecisionStatus.ALLOWED:
            self._repository.save_autonomy_run(record)
            return decision

        operation = self._runbook_operation_service.request(
            runbook_name,
            parameters=parameters,
            requester="datasentry-autonomy",
            incident_id=incident_id,
        )
        approved = self._runbook_operation_service.approve(
            operation.id,
            approver="datasentry-autonomy",
        )
        executed = self._runbook_operation_service.execute(
            approved.id,
            actor="datasentry-autonomy",
        )
        decision.operation_id = executed.id
        record = record.model_copy(
            update={
                "operation_id": executed.id,
                "finished_at": self._clock(),
                "succeeded": executed.status is OperationStatus.SUCCEEDED,
            },
        )
        self._repository.save_autonomy_run(record)
        self._repository.update_autonomy_run(record)
        return decision
```

Update `src/datasentry/autonomy/__init__.py` to export `AutonomyService`.

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
.venv/bin/pytest tests/unit/autonomy/test_service.py tests/unit/autonomy/test_policy.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/datasentry/autonomy tests/unit/autonomy/test_service.py
git commit -m "feat: 增加M7自治服务"
```

---

## Task 5: FastAPI Autonomy Routes

**Files:**
- Create: `src/datasentry/api/routes/autonomy.py`
- Modify: `src/datasentry/api/schemas.py`
- Modify: `src/datasentry/api/dependencies.py`
- Modify: `src/datasentry/api/app.py`
- Test: `tests/integration/api/test_autonomy_api.py`

- [ ] **Step 1: Write failing API tests**

Add `tests/integration/api/test_autonomy_api.py`:

```python
from fastapi.testclient import TestClient

from datasentry.api import create_app


def test_list_autonomy_policies_returns_default_shadow_policy(api_database_path) -> None:
    app = create_app(database_path=api_database_path)
    client = TestClient(app)

    response = client.get("/api/autonomy/policies")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["runbook_name"] == "mock.restart_preview"
    assert payload[0]["enabled"] is False
    assert payload[0]["shadow_mode"] is True


def test_evaluate_autonomy_candidate_returns_shadow_decision(api_database_path) -> None:
    app = create_app(database_path=api_database_path)
    client = TestClient(app)

    response = client.post(
        "/api/autonomy/evaluate",
        json={
            "runbook_name": "mock.restart_preview",
            "parameters": {"target": "api", "reason": "演练"},
            "incident_id": None,
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "blocked"
    assert response.json()["reason_code"] == "policy.disabled"


def test_execute_autonomy_candidate_does_not_create_operation_when_shadowed(api_database_path) -> None:
    app = create_app(database_path=api_database_path)
    client = TestClient(app)
    client.patch(
        "/api/autonomy/policies/mock.restart_preview",
        json={"enabled": True, "shadow_mode": True},
    )

    response = client.post(
        "/api/autonomy/execute",
        json={
            "runbook_name": "mock.restart_preview",
            "parameters": {"target": "api", "reason": "演练"},
            "incident_id": None,
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "shadowed"
    runs = client.get("/api/autonomy/runs").json()
    assert runs[0]["decision_status"] == "shadowed"
    assert runs[0]["operation_id"] is None
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
.venv/bin/pytest tests/integration/api/test_autonomy_api.py -q
```

Expected: FAIL because routes are missing.

- [ ] **Step 3: Add schemas and routes**

Add these schemas to `src/datasentry/api/schemas.py`:

```python
class AutonomyCandidateRequest(BaseModel):
    runbook_name: str
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    incident_id: str | None = None


class AutonomyPolicyUpdateRequest(BaseModel):
    enabled: bool | None = None
    shadow_mode: bool | None = None
```

Create `src/datasentry/api/routes/autonomy.py`:

```python
"""有限自治 API。"""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder

from datasentry.api.dependencies import get_autonomy_service, get_repository
from datasentry.api.schemas import AutonomyCandidateRequest, AutonomyPolicyUpdateRequest
from datasentry.autonomy import BuiltInAutonomyPolicyCatalog
from datasentry.storage import SQLiteRepository

router = APIRouter(prefix="/autonomy", tags=["autonomy"])


@router.get("/policies")
def list_policies(repository: Annotated[SQLiteRepository, Depends(get_repository)]) -> list[dict[str, object]]:
    _ensure_default_policies(repository)
    return cast(list[dict[str, object]], jsonable_encoder(repository.list_autonomy_policies()))


@router.get("/policies/{runbook_name}")
def get_policy(runbook_name: str, repository: Annotated[SQLiteRepository, Depends(get_repository)]) -> dict[str, object]:
    _ensure_default_policies(repository)
    return cast(dict[str, object], jsonable_encoder(repository.get_autonomy_policy(runbook_name)))


@router.patch("/policies/{runbook_name}")
def update_policy(runbook_name: str, request: AutonomyPolicyUpdateRequest, repository: Annotated[SQLiteRepository, Depends(get_repository)]) -> dict[str, object]:
    _ensure_default_policies(repository)
    policy = repository.get_autonomy_policy(runbook_name)
    updates = {}
    if request.enabled is not None:
        updates["enabled"] = request.enabled
    if request.shadow_mode is not None:
        updates["shadow_mode"] = request.shadow_mode
    updated = policy.model_copy(update=updates)
    repository.save_autonomy_policy(updated)
    return cast(dict[str, object], jsonable_encoder(updated))


@router.post("/evaluate")
def evaluate_candidate(request: AutonomyCandidateRequest, service=Depends(get_autonomy_service)) -> dict[str, object]:
    decision = service.evaluate_candidate(
        request.runbook_name,
        parameters=request.parameters,
        incident_id=request.incident_id,
    )
    return cast(dict[str, object], jsonable_encoder(decision))


@router.post("/execute")
def execute_candidate(request: AutonomyCandidateRequest, service=Depends(get_autonomy_service)) -> dict[str, object]:
    decision = service.execute_candidate(
        request.runbook_name,
        parameters=request.parameters,
        incident_id=request.incident_id,
    )
    return cast(dict[str, object], jsonable_encoder(decision))


@router.get("/runs")
def list_runs(
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], jsonable_encoder(repository.list_autonomy_runs(limit=limit)))


def _ensure_default_policies(repository: SQLiteRepository) -> None:
    existing = {policy.runbook_name for policy in repository.list_autonomy_policies()}
    for policy in BuiltInAutonomyPolicyCatalog().list_policies():
        if policy.runbook_name not in existing:
            repository.save_autonomy_policy(policy)
```

Wire `get_autonomy_service` in dependencies and include the router in `create_app`.

- [ ] **Step 4: Run API tests**

Run:

```bash
.venv/bin/pytest tests/integration/api/test_autonomy_api.py tests/integration/api/test_runbooks_api.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/datasentry/api tests/integration/api/test_autonomy_api.py
git commit -m "feat: 暴露M7自治API"
```

---

## Task 6: React Autonomy Panel

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/ApprovalsPage.tsx`
- Modify: `frontend/src/styles/app.css`

- [ ] **Step 1: Add API types**

In `frontend/src/api/types.ts`, add:

```typescript
export interface AutonomyPolicy {
  runbook_name: string;
  enabled: boolean;
  shadow_mode: boolean;
  circuit_breaker_state: 'closed' | 'open' | 'half_open';
  min_success_rate: number;
  min_success_samples: number;
  failure_threshold: number;
}

export interface AutonomyDecision {
  status: 'allowed' | 'shadowed' | 'blocked' | 'escalated';
  reason_code: string;
  reason: string;
  runbook_name: string;
  target?: string | null;
  incident_id?: string | null;
  operation_id?: string | null;
}

export interface AutonomyRunRecord {
  id: string;
  runbook_name: string;
  target: string;
  incident_id?: string | null;
  operation_id?: string | null;
  decision_status: 'allowed' | 'shadowed' | 'blocked' | 'escalated';
  reason_code: string;
  reason: string;
  created_at: string;
  finished_at?: string | null;
  succeeded?: boolean | null;
}
```

- [ ] **Step 2: Add client methods**

In `frontend/src/api/client.ts`, add:

```typescript
export async function listAutonomyPolicies(): Promise<AutonomyPolicy[]> {
  return request<AutonomyPolicy[]>('/api/autonomy/policies');
}

export async function updateAutonomyPolicy(
  runbookName: string,
  payload: { enabled?: boolean; shadow_mode?: boolean },
): Promise<AutonomyPolicy> {
  return request<AutonomyPolicy>(`/api/autonomy/policies/${runbookName}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export async function executeAutonomyCandidate(payload: {
  runbook_name: string;
  parameters: Record<string, unknown>;
  incident_id?: string | null;
}): Promise<AutonomyDecision> {
  return request<AutonomyDecision>('/api/autonomy/execute', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function listAutonomyRuns(): Promise<AutonomyRunRecord[]> {
  return request<AutonomyRunRecord[]>('/api/autonomy/runs');
}
```

- [ ] **Step 3: Add autonomy panel to approval page**

In `frontend/src/pages/ApprovalsPage.tsx`, add state for policies and runs, load them beside existing Runbook data, and render a compact panel:

```tsx
<section className="panel autonomy-panel">
  <div className="panel-heading">
    <h2>有限自治</h2>
    <button className="icon-button" type="button" onClick={refreshAutonomy}>
      <RefreshCcw size={16} />
    </button>
  </div>
  <div className="autonomy-grid">
    {autonomyPolicies.map((policy) => (
      <article className="autonomy-row" key={policy.runbook_name}>
        <div>
          <strong>{policy.runbook_name}</strong>
          <span>{policy.circuit_breaker_state}</span>
        </div>
        <label>
          <input
            type="checkbox"
            checked={policy.enabled}
            onChange={(event) =>
              handlePolicyChange(policy.runbook_name, { enabled: event.target.checked })
            }
          />
          启用
        </label>
        <label>
          <input
            type="checkbox"
            checked={policy.shadow_mode}
            onChange={(event) =>
              handlePolicyChange(policy.runbook_name, { shadow_mode: event.target.checked })
            }
          />
          Shadow
        </label>
        <button type="button" onClick={() => handleAutonomyExecute(policy.runbook_name)}>
          演练
        </button>
      </article>
    ))}
  </div>
  <div className="decision-list">
    {autonomyRuns.slice(0, 5).map((run) => (
      <div className="decision-row" key={run.id}>
        <span>{run.decision_status}</span>
        <strong>{run.runbook_name}</strong>
        <small>{run.reason}</small>
      </div>
    ))}
  </div>
</section>
```

Use existing page patterns for error state and refresh behavior. Keep all visible text in Chinese.

- [ ] **Step 4: Add CSS**

In `frontend/src/styles/app.css`, add compact styles for `.autonomy-panel`, `.autonomy-grid`, `.autonomy-row`, and `.decision-row` using the existing color tokens and 8px or smaller border radius.

- [ ] **Step 5: Run frontend verification**

Run:

```bash
cd frontend && npm run typecheck
cd frontend && npm run build
```

Expected: both commands pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/api/client.ts frontend/src/pages/ApprovalsPage.tsx frontend/src/styles/app.css
git commit -m "feat: 增加M7自治控制台"
```

---

## Task 7: Documentation, Status, And Final Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/PROJECT_STATUS.md`

- [ ] **Step 1: Update README**

Add an `M7 有限自治` section after the M6 section:

```markdown
## M7 有限自治

M7 第一版增加本地有限自治控制层，默认策略为 disabled + shadow，不会自动执行真实生产操作。
本阶段只允许 mock Runbook 参与自治评估，所有真实 SSH、Shell、SQL 写入、Savepoint、
补数、配置修改和删除数据仍被禁止。

本地演练流程：

1. 启动 DataSentry API。
2. 在审批页面查看“有限自治”区域。
3. 打开 `mock.restart_preview` 的 shadow 策略并执行演练。
4. 确认页面只记录 shadow 决策，不创建 Operation。
5. 关闭 shadow 后再次演练，确认仅本地 mock Operation 会自动创建、批准、执行和验证。

M7 开发不要求打开云实例。云端或测试环境只用于后续只读 smoke、人工审批低风险演练、
成功率样本收集和生产自治评估。
```

- [ ] **Step 2: Update project status**

Update `docs/PROJECT_STATUS.md`:

- Current stage: `M7：有限自治开发中`
- Current work: M7 本地自治控制层实施中
- Known boundary: no cloud instance required for local development
- Key docs: add M7 design and plan
- Change log: add M7 design/plan and implementation start

- [ ] **Step 3: Run final backend verification**

Run:

```bash
.venv/bin/ruff format --check .
.venv/bin/ruff check .
.venv/bin/mypy src
.venv/bin/pytest tests -q -W error::ResourceWarning --cov=datasentry --cov-report=term-missing --cov-fail-under=90
```

Expected: all pass; pytest coverage remains at or above 90%.

- [ ] **Step 4: Run final frontend verification**

Run:

```bash
cd frontend && npm run typecheck
cd frontend && npm run build
```

Expected: both pass.

- [ ] **Step 5: Inspect diff for secrets and boundary regressions**

Run:

```bash
git diff --check
rg -n "password|token|secret|AKIA|BEGIN .*PRIVATE KEY|自动补数|自动 Savepoint|生产写操作已执行|root key" README.md docs src tests frontend
```

Expected: no secrets. Mentions of forbidden operations only appear as documented prohibitions or tests.

- [ ] **Step 6: Commit**

```bash
git add README.md docs/PROJECT_STATUS.md
git commit -m "docs: 更新M7有限自治状态"
```

---

## Execution Notes

- Keep all Python identifiers, JSON fields, API paths, database columns, and TypeScript identifiers in clear English.
- Keep developer-facing comments, docstrings, API messages, README text, and UI copy in Chinese.
- Do not add a real SSH, Shell, SQL write, Ansible, Savepoint,补数, or production configuration executor in M7 first pass.
- Do not open a cloud instance for local development. Cloud work is only for later smoke and controlled maintenance-window evidence gathering.
- Preserve M6 `RunbookOperationService` as the only path that creates, approves, executes, verifies, and audits Operations.
