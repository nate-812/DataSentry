# M6 Approval Runbooks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first M6 approval-runbook loop with versioned mock Runbooks, Operation approval, auditable execution, idempotency, locks, and mock post-operation verification.

**Architecture:** Add a focused `datasentry.runbooks` package for Runbook definitions, policy, mock execution, verification, and Operation orchestration. Extend SQLite with runbook snapshots, operation audit events, operation locks, and operation idempotency keys while preserving the existing `Operation` model and M4 simulation API compatibility. Extend FastAPI and the React approval page so local users can create, approve, execute, reject, cancel, and inspect mock Runbook Operations without touching production systems.

**Tech Stack:** Python 3.12, Pydantic v2, SQLite migrations, FastAPI, pytest, React, TypeScript, Vite, lucide-react.

---

## File Structure

- Create `src/datasentry/runbooks/models.py`: Runbook, OperationEvent, OperationLock, execution result, verification result, and enum models.
- Create `src/datasentry/runbooks/catalog.py`: built-in Runbook definitions and lookup helpers.
- Create `src/datasentry/runbooks/policy.py`: risk and execution-mode policy checks.
- Create `src/datasentry/runbooks/idempotency.py`: stable idempotency and lock key rendering.
- Create `src/datasentry/runbooks/executor.py`: executor protocol and `MockRunbookExecutor`.
- Create `src/datasentry/runbooks/verifier.py`: verifier protocol and `MockOperationVerifier`.
- Create `src/datasentry/runbooks/service.py`: Operation request, approval, rejection, execution, verification, cancellation orchestration.
- Create `src/datasentry/runbooks/__init__.py`: package exports.
- Create `src/datasentry/storage/sql/0005_approval_runbooks.sql`: M6 schema migration.
- Modify `src/datasentry/domain/operation.py`: add `idempotency_key` field while keeping existing callers valid.
- Modify `src/datasentry/storage/repository.py`: add protocol methods for runbooks, operation events, locks, and idempotency lookup.
- Modify `src/datasentry/storage/sqlite.py`: persist M6 models and the new Operation idempotency field.
- Modify `src/datasentry/api/schemas.py`: add Runbook and Operation request/action response models.
- Create `src/datasentry/api/routes/runbooks.py`: Runbook list/detail routes.
- Modify `src/datasentry/api/routes/operations.py`: replace simulation-only service with M6 service while preserving simulation endpoint.
- Modify `src/datasentry/api/dependencies.py`: provide `RunbookOperationService`.
- Modify `src/datasentry/api/app.py`: include runbook router.
- Modify `src/datasentry/operations/simulation.py`: turn the M4 simulation service into a compatibility wrapper that calls `RunbookOperationService`.
- Modify `src/datasentry/operations/__init__.py`: export compatibility names.
- Modify `frontend/src/api/types.ts`: add Runbook, OperationEvent, extended Operation fields.
- Modify `frontend/src/api/client.ts`: add runbook, operation create, execute, cancel, event API calls.
- Modify `frontend/src/pages/ApprovalsPage.tsx`: upgrade to a Runbook operation console.
- Modify `frontend/src/styles/app.css`: add compact controls for the upgraded approval page.
- Modify `README.md`: document M6 local mock usage and cloud boundary.
- Modify `docs/PROJECT_STATUS.md`: record M6 implementation status and verification results.

---

## Task 1: Runbook Domain Models And Built-In Catalog

**Files:**
- Create: `src/datasentry/runbooks/models.py`
- Create: `src/datasentry/runbooks/catalog.py`
- Create: `src/datasentry/runbooks/__init__.py`
- Test: `tests/unit/runbooks/test_catalog.py`
- Test: `tests/unit/runbooks/test_models.py`

- [ ] **Step 1: Write failing catalog/model tests**

Add `tests/unit/runbooks/test_catalog.py`:

```python
import pytest

from datasentry.domain import OperationRisk
from datasentry.errors import NotFoundError
from datasentry.runbooks import BuiltInRunbookCatalog, ExecutionMode


def test_builtin_catalog_lists_mock_runbooks_and_forbidden_guard() -> None:
    catalog = BuiltInRunbookCatalog()

    runbooks = catalog.list_runbooks()

    assert [item.name for item in runbooks] == [
        "mock.restart_preview",
        "mock.clear_cache_preview",
        "forbidden.shell_command",
    ]
    assert runbooks[0].risk is OperationRisk.L1
    assert runbooks[0].execution_mode is ExecutionMode.MOCK
    assert runbooks[2].risk is OperationRisk.FORBIDDEN
    assert runbooks[2].execution_mode is ExecutionMode.FORBIDDEN


def test_builtin_catalog_returns_copy_by_name() -> None:
    catalog = BuiltInRunbookCatalog()

    runbook = catalog.get("mock.restart_preview")

    assert runbook.name == "mock.restart_preview"
    assert runbook.parameter_schema["required"] == ["target", "reason"]
    assert runbook.enabled is True


def test_builtin_catalog_rejects_unknown_runbook() -> None:
    catalog = BuiltInRunbookCatalog()

    with pytest.raises(NotFoundError, match="未找到指定 Runbook"):
        catalog.get("missing.runbook")
```

Add `tests/unit/runbooks/test_models.py`:

```python
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
    with pytest.raises(ValueError, match="mock|forbidden"):
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
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
.venv/bin/pytest tests/unit/runbooks/test_catalog.py tests/unit/runbooks/test_models.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'datasentry.runbooks'`.

- [ ] **Step 3: Implement models and catalog**

Create `src/datasentry/runbooks/models.py` with these public types:

```python
"""审批式 Runbook 的领域模型。"""

from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import Field, JsonValue, field_validator, model_validator

from datasentry.domain import OperationRisk
from datasentry.domain.common import (
    DomainModel,
    new_id,
    normalize_optional_datetime,
    require_aware_datetime,
    utc_now,
)
from datasentry.redaction import redact_value


class ExecutionMode(StrEnum):
    MOCK = "mock"
    FORBIDDEN = "forbidden"


class OperationEventType(StrEnum):
    OPERATION_REQUESTED = "operation_requested"
    POLICY_EVALUATED = "policy_evaluated"
    IDEMPOTENCY_REUSED = "idempotency_reused"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_REJECTED = "approval_rejected"
    EXECUTION_STARTED = "execution_started"
    EXECUTOR_OUTPUT_RECORDED = "executor_output_recorded"
    VERIFICATION_STARTED = "verification_started"
    VERIFICATION_SUCCEEDED = "verification_succeeded"
    VERIFICATION_FAILED = "verification_failed"
    OPERATION_FAILED = "operation_failed"
    OPERATION_CANCELLED = "operation_cancelled"


class Runbook(DomainModel):
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    risk: OperationRisk
    execution_mode: ExecutionMode
    parameter_schema: dict[str, JsonValue] = Field(default_factory=dict)
    precheck: dict[str, JsonValue] = Field(default_factory=dict)
    postcheck: dict[str, JsonValue] = Field(default_factory=dict)
    lock_key_template: str = Field(min_length=1)
    idempotency_key_template: str = Field(min_length=1)
    enabled: bool = True
    audit_notes: str | None = None

    @model_validator(mode="after")
    def validate_runbook(self) -> Self:
        if self.execution_mode is ExecutionMode.FORBIDDEN and self.risk is not OperationRisk.FORBIDDEN:
            raise ValueError("禁止执行模式必须使用 forbidden 风险等级")
        return self


class OperationEvent(DomainModel):
    id: str = Field(default_factory=new_id)
    operation_id: str = Field(min_length=1)
    event_type: OperationEventType
    summary: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)

    _normalize_created_at = field_validator("created_at")(require_aware_datetime)

    @field_validator("payload")
    @classmethod
    def redact_payload(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        redacted = redact_value(value)
        assert isinstance(redacted, dict)
        return redacted


class OperationLock(DomainModel):
    lock_key: str = Field(min_length=1)
    operation_id: str = Field(min_length=1)
    runbook_name: str = Field(min_length=1)
    target: str = Field(min_length=1)
    acquired_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime
    released_at: datetime | None = None

    _normalize_acquired_at = field_validator("acquired_at")(require_aware_datetime)
    _normalize_expires_at = field_validator("expires_at")(require_aware_datetime)
    _normalize_released_at = field_validator("released_at")(normalize_optional_datetime)

    @model_validator(mode="after")
    def validate_lock_times(self) -> Self:
        if self.expires_at <= self.acquired_at:
            raise ValueError("锁过期时间必须晚于获取时间")
        if self.released_at is not None and self.released_at < self.acquired_at:
            raise ValueError("锁释放时间不能早于获取时间")
        return self


class RunbookExecutionResult(DomainModel):
    status: str = Field(pattern="^(succeeded|failed)$")
    summary: str = Field(min_length=1)
    details: dict[str, JsonValue] = Field(default_factory=dict)
    started_at: datetime
    finished_at: datetime


class RunbookVerificationResult(DomainModel):
    status: str = Field(pattern="^(succeeded|failed)$")
    summary: str = Field(min_length=1)
    details: dict[str, JsonValue] = Field(default_factory=dict)
    verified_at: datetime
```

Create `src/datasentry/runbooks/catalog.py` with a `BuiltInRunbookCatalog` that returns copies of three `Runbook` instances named `mock.restart_preview`, `mock.clear_cache_preview`, and `forbidden.shell_command`.

Create `src/datasentry/runbooks/__init__.py` exporting the public types.

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
.venv/bin/pytest tests/unit/runbooks/test_catalog.py tests/unit/runbooks/test_models.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/datasentry/runbooks tests/unit/runbooks
git commit -m "feat: 增加M6 Runbook领域模型"
```

---

## Task 2: Operation Idempotency Field

**Files:**
- Modify: `src/datasentry/domain/operation.py`
- Modify: `src/datasentry/storage/sql/0005_approval_runbooks.sql`
- Modify: `src/datasentry/storage/sqlite.py`
- Test: `tests/unit/domain/test_operation.py`
- Test: `tests/integration/storage/test_migrations.py`
- Test: `tests/integration/storage/test_sqlite_repository.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/domain/test_operation.py`:

```python
def test_operation_accepts_optional_idempotency_key(observed_at: datetime) -> None:
    operation = Operation(
        name="mock.restart_preview",
        version="1.0.0",
        parameters={"target": "api", "reason": "演练"},
        risk=OperationRisk.L1,
        requester="operator",
        idempotency_key="mock.restart_preview:1.0.0:api:none",
        requested_at=observed_at,
    )

    assert operation.idempotency_key == "mock.restart_preview:1.0.0:api:none"
```

Append to `tests/integration/storage/test_sqlite_repository.py`:

```python
def test_operation_idempotency_key_round_trips(repository: SQLiteRepository) -> None:
    operation = Operation(
        name="mock.restart_preview",
        version="1.0.0",
        parameters={"target": "api", "reason": "演练"},
        risk=OperationRisk.L1,
        requester="operator",
        idempotency_key="mock.restart_preview:1.0.0:api:none",
    )

    repository.save_operation(operation)

    assert repository.get_operation(operation.id).idempotency_key == operation.idempotency_key
```

Append to `tests/integration/storage/test_migrations.py`:

```python
def test_migration_0005_adds_operation_idempotency_key(tmp_path) -> None:
    database_path = tmp_path / "datasentry.db"

    upgrade_database(database_path)

    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(operations)").fetchall()
        }
    assert "idempotency_key" in columns
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
.venv/bin/pytest tests/unit/domain/test_operation.py::test_operation_accepts_optional_idempotency_key tests/integration/storage/test_migrations.py::test_migration_0005_adds_operation_idempotency_key tests/integration/storage/test_sqlite_repository.py::test_operation_idempotency_key_round_trips -q
```

Expected: FAIL because `Operation` and the database do not have `idempotency_key`.

- [ ] **Step 3: Add Operation field and migration**

Modify `src/datasentry/domain/operation.py`:

```python
    idempotency_key: str | None = None
```

Add `src/datasentry/storage/sql/0005_approval_runbooks.sql`:

```sql
ALTER TABLE operations ADD COLUMN idempotency_key TEXT;

CREATE UNIQUE INDEX idx_operations_idempotency_key_active
    ON operations(idempotency_key)
    WHERE idempotency_key IS NOT NULL
      AND status IN ('requested', 'awaiting_approval', 'approved', 'running', 'verifying');
```

Update `src/datasentry/storage/sqlite.py` operation insert, update, values, and row conversion to include `idempotency_key`.

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
.venv/bin/pytest tests/unit/domain/test_operation.py::test_operation_accepts_optional_idempotency_key tests/integration/storage/test_migrations.py::test_migration_0005_adds_operation_idempotency_key tests/integration/storage/test_sqlite_repository.py::test_operation_idempotency_key_round_trips -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/datasentry/domain/operation.py src/datasentry/storage/sql/0005_approval_runbooks.sql src/datasentry/storage/sqlite.py tests/unit/domain/test_operation.py tests/integration/storage/test_migrations.py tests/integration/storage/test_sqlite_repository.py
git commit -m "feat: 增加Operation幂等键"
```

---

## Task 3: Repository Support For Runbooks, Events, And Locks

**Files:**
- Modify: `src/datasentry/storage/sql/0005_approval_runbooks.sql`
- Modify: `src/datasentry/storage/repository.py`
- Modify: `src/datasentry/storage/sqlite.py`
- Test: `tests/integration/storage/test_sqlite_repository.py`

- [ ] **Step 1: Write failing repository tests**

Append to `tests/integration/storage/test_sqlite_repository.py`:

```python
from datetime import timedelta

from datasentry.runbooks import (
    BuiltInRunbookCatalog,
    OperationEvent,
    OperationEventType,
    OperationLock,
)


def test_runbook_snapshot_event_and_lock_round_trip(repository: SQLiteRepository) -> None:
    runbook = BuiltInRunbookCatalog().get("mock.restart_preview")
    operation = Operation(
        name=runbook.name,
        version=runbook.version,
        parameters={"target": "api", "reason": "演练"},
        risk=runbook.risk,
        requester="operator",
        idempotency_key="mock.restart_preview:1.0.0:api:none",
    )
    event = OperationEvent(
        operation_id=operation.id,
        event_type=OperationEventType.OPERATION_REQUESTED,
        summary="创建 Runbook 操作",
        actor="operator",
        payload={"target": "api"},
    )
    lock = OperationLock(
        lock_key="runbook:mock.restart_preview:api",
        operation_id=operation.id,
        runbook_name=runbook.name,
        target="api",
        expires_at=operation.requested_at + timedelta(minutes=5),
    )

    repository.save_runbook(runbook)
    repository.save_operation(operation)
    repository.save_operation_event(event)
    repository.acquire_operation_lock(lock)

    assert repository.list_runbooks() == [runbook]
    assert repository.get_runbook(runbook.name) == runbook
    assert repository.list_operation_events(operation.id) == [event]
    assert repository.get_active_operation_by_idempotency_key(operation.idempotency_key) == operation
    assert repository.get_active_lock(lock.lock_key) == lock

    repository.release_operation_lock(lock.lock_key, released_at=operation.requested_at + timedelta(minutes=1))

    assert repository.get_active_lock(lock.lock_key) is None
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
.venv/bin/pytest tests/integration/storage/test_sqlite_repository.py::test_runbook_snapshot_event_and_lock_round_trip -q
```

Expected: FAIL because repository methods and tables are missing.

- [ ] **Step 3: Extend migration and repository protocol**

Extend `src/datasentry/storage/sql/0005_approval_runbooks.sql` with:

```sql
CREATE TABLE runbooks (
    name TEXT PRIMARY KEY,
    version TEXT NOT NULL CHECK (length(trim(version)) > 0),
    title TEXT NOT NULL CHECK (length(trim(title)) > 0),
    description TEXT NOT NULL CHECK (length(trim(description)) > 0),
    risk TEXT NOT NULL CHECK (risk IN ('L0', 'L1', 'L2', 'L3', 'forbidden')),
    execution_mode TEXT NOT NULL CHECK (execution_mode IN ('mock', 'forbidden')),
    parameter_schema_json TEXT NOT NULL,
    precheck_json TEXT NOT NULL,
    postcheck_json TEXT NOT NULL,
    lock_key_template TEXT NOT NULL CHECK (length(trim(lock_key_template)) > 0),
    idempotency_key_template TEXT NOT NULL CHECK (length(trim(idempotency_key_template)) > 0),
    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
    audit_notes TEXT
);

CREATE TABLE operation_events (
    id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    summary TEXT NOT NULL CHECK (length(trim(summary)) > 0),
    actor TEXT NOT NULL CHECK (length(trim(actor)) > 0),
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (operation_id) REFERENCES operations(id) ON DELETE CASCADE
);

CREATE TABLE operation_locks (
    lock_key TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL,
    runbook_name TEXT NOT NULL CHECK (length(trim(runbook_name)) > 0),
    target TEXT NOT NULL CHECK (length(trim(target)) > 0),
    acquired_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    released_at TEXT,
    FOREIGN KEY (operation_id) REFERENCES operations(id) ON DELETE CASCADE
);

CREATE INDEX idx_operation_events_operation_id_created_at
    ON operation_events(operation_id, created_at);
CREATE INDEX idx_operation_locks_active
    ON operation_locks(lock_key)
    WHERE released_at IS NULL;
```

Add methods to `Repository` protocol: `save_runbook`, `get_runbook`, `list_runbooks`, `save_operation_event`, `list_operation_events`, `get_active_operation_by_idempotency_key`, `acquire_operation_lock`, `get_active_lock`, `release_operation_lock`.

- [ ] **Step 4: Implement SQLite methods and row converters**

Update `src/datasentry/storage/sqlite.py` imports and adapters for Runbook models. Store all JSON through `_dump_json(redact_value(...))` where payloads may contain user data. Use `INSERT OR REPLACE` for `save_runbook`, ordered `SELECT * FROM runbooks ORDER BY name`, and `released_at IS NULL AND expires_at > ?` for active locks.

- [ ] **Step 5: Run test to verify GREEN**

Run:

```bash
.venv/bin/pytest tests/integration/storage/test_sqlite_repository.py::test_runbook_snapshot_event_and_lock_round_trip -q
```

Expected: PASS.

- [ ] **Step 6: Run migration test file**

Run:

```bash
.venv/bin/pytest tests/integration/storage/test_migrations.py tests/integration/storage/test_sqlite_repository.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/datasentry/storage/sql/0005_approval_runbooks.sql src/datasentry/storage/repository.py src/datasentry/storage/sqlite.py tests/integration/storage/test_sqlite_repository.py tests/integration/storage/test_migrations.py
git commit -m "feat: 持久化Runbook审计与锁"
```

---

## Task 4: Policy, Idempotency, Mock Executor, And Verifier

**Files:**
- Create: `src/datasentry/runbooks/policy.py`
- Create: `src/datasentry/runbooks/idempotency.py`
- Create: `src/datasentry/runbooks/executor.py`
- Create: `src/datasentry/runbooks/verifier.py`
- Modify: `src/datasentry/runbooks/__init__.py`
- Test: `tests/unit/runbooks/test_policy.py`
- Test: `tests/unit/runbooks/test_idempotency.py`
- Test: `tests/unit/runbooks/test_executor_verifier.py`

- [ ] **Step 1: Write failing tests**

Add `tests/unit/runbooks/test_policy.py`:

```python
import pytest

from datasentry.errors import DataSentryError
from datasentry.runbooks import BuiltInRunbookCatalog, RunbookPolicy


def test_policy_allows_enabled_mock_l1_runbook() -> None:
    runbook = BuiltInRunbookCatalog().get("mock.restart_preview")

    RunbookPolicy().assert_request_allowed(runbook)


def test_policy_rejects_forbidden_runbook() -> None:
    runbook = BuiltInRunbookCatalog().get("forbidden.shell_command")

    with pytest.raises(DataSentryError) as error:
        RunbookPolicy().assert_request_allowed(runbook)

    assert error.value.code == "runbook.forbidden"
```

Add `tests/unit/runbooks/test_idempotency.py`:

```python
from datasentry.runbooks import BuiltInRunbookCatalog, render_idempotency_key, render_lock_key


def test_render_idempotency_key_is_stable() -> None:
    runbook = BuiltInRunbookCatalog().get("mock.restart_preview")

    key = render_idempotency_key(
        runbook,
        parameters={"reason": "演练", "target": "api"},
        incident_id=None,
    )

    assert key == "mock.restart_preview:1.0.0:api:none"


def test_render_lock_key_uses_target() -> None:
    runbook = BuiltInRunbookCatalog().get("mock.restart_preview")

    assert render_lock_key(runbook, {"target": "api"}) == "runbook:mock.restart_preview:api"
```

Add `tests/unit/runbooks/test_executor_verifier.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
.venv/bin/pytest tests/unit/runbooks/test_policy.py tests/unit/runbooks/test_idempotency.py tests/unit/runbooks/test_executor_verifier.py -q
```

Expected: FAIL because policy/idempotency/executor/verifier modules are missing.

- [ ] **Step 3: Implement policy/idempotency/executor/verifier**

Implement:

- `RunbookPolicy.assert_request_allowed(runbook)` rejects disabled, forbidden, and non-mock runbooks with `DataSentryError`.
- `render_idempotency_key(runbook, parameters, incident_id)` supports `{name}`, `{version}`, `{target}`, `{incident_id}`.
- `render_lock_key(runbook, parameters)` supports `{name}` and `{target}`.
- `MockRunbookExecutor.execute(runbook, operation)` returns deterministic success for built-in mock runbooks.
- `MockOperationVerifier.verify(runbook, operation)` returns deterministic success from `postcheck`.

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
.venv/bin/pytest tests/unit/runbooks/test_policy.py tests/unit/runbooks/test_idempotency.py tests/unit/runbooks/test_executor_verifier.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/datasentry/runbooks tests/unit/runbooks
git commit -m "feat: 增加Runbook策略和mock执行器"
```

---

## Task 5: Runbook Operation Service

**Files:**
- Create: `src/datasentry/runbooks/service.py`
- Modify: `src/datasentry/runbooks/__init__.py`
- Test: `tests/unit/runbooks/test_service.py`

- [ ] **Step 1: Write failing service tests**

Add `tests/unit/runbooks/test_service.py` with an in-memory fake repository:

```python
from datetime import UTC, datetime, timedelta

import pytest

from datasentry.domain import OperationStatus
from datasentry.errors import DataSentryError
from datasentry.runbooks import (
    BuiltInRunbookCatalog,
    MockOperationVerifier,
    MockRunbookExecutor,
    RunbookOperationService,
)


class FakeRunbookRepository:
    def __init__(self) -> None:
        self.operations = {}
        self.events = []
        self.locks = {}
        self.runbooks = {}

    def save_runbook(self, runbook):
        self.runbooks[runbook.name] = runbook

    def save_operation(self, operation):
        self.operations[operation.id] = operation

    def update_operation(self, operation):
        self.operations[operation.id] = operation

    def get_operation(self, operation_id):
        return self.operations[operation_id]

    def save_operation_event(self, event):
        self.events.append(event)

    def list_operation_events(self, operation_id):
        return [event for event in self.events if event.operation_id == operation_id]

    def get_active_operation_by_idempotency_key(self, key):
        return next(
            (
                operation
                for operation in self.operations.values()
                if operation.idempotency_key == key
                and operation.status
                in {
                    OperationStatus.REQUESTED,
                    OperationStatus.AWAITING_APPROVAL,
                    OperationStatus.APPROVED,
                    OperationStatus.RUNNING,
                    OperationStatus.VERIFYING,
                }
            ),
            None,
        )

    def acquire_operation_lock(self, lock):
        if lock.lock_key in self.locks and self.locks[lock.lock_key].released_at is None:
            raise DataSentryError(code="operation.lock_conflict", message="操作锁已被占用")
        self.locks[lock.lock_key] = lock

    def release_operation_lock(self, lock_key, *, released_at):
        current = self.locks[lock_key]
        self.locks[lock_key] = current.model_copy(update={"released_at": released_at})


def service(repository):
    clock_values = iter(
        [
            datetime(2026, 6, 28, 10, 0, tzinfo=UTC),
            datetime(2026, 6, 28, 10, 1, tzinfo=UTC),
            datetime(2026, 6, 28, 10, 2, tzinfo=UTC),
            datetime(2026, 6, 28, 10, 3, tzinfo=UTC),
            datetime(2026, 6, 28, 10, 4, tzinfo=UTC),
        ]
    )
    return RunbookOperationService(
        repository=repository,
        catalog=BuiltInRunbookCatalog(),
        executor=MockRunbookExecutor(clock=lambda: datetime(2026, 6, 28, 10, 2, tzinfo=UTC)),
        verifier=MockOperationVerifier(clock=lambda: datetime(2026, 6, 28, 10, 3, tzinfo=UTC)),
        clock=lambda: next(clock_values),
        lock_ttl=timedelta(minutes=5),
    )


def test_request_approve_execute_records_full_audit_flow() -> None:
    repository = FakeRunbookRepository()
    operation_service = service(repository)

    operation = operation_service.request(
        runbook_name="mock.restart_preview",
        parameters={"target": "api", "reason": "演练"},
        requester="operator",
        incident_id=None,
    )
    approved = operation_service.approve(operation.id, approver="operator")
    executed = operation_service.execute(operation.id, actor="operator")

    assert operation.status is OperationStatus.AWAITING_APPROVAL
    assert approved.status is OperationStatus.APPROVED
    assert executed.status is OperationStatus.SUCCEEDED
    assert executed.result["verification"]["status"] == "succeeded"
    assert [event.event_type.value for event in repository.list_operation_events(operation.id)] == [
        "operation_requested",
        "policy_evaluated",
        "approval_granted",
        "execution_started",
        "executor_output_recorded",
        "verification_started",
        "verification_succeeded",
    ]


def test_request_reuses_active_operation_by_idempotency_key() -> None:
    repository = FakeRunbookRepository()
    operation_service = service(repository)

    first = operation_service.request(
        runbook_name="mock.restart_preview",
        parameters={"target": "api", "reason": "演练"},
        requester="operator",
        incident_id=None,
    )
    second = operation_service.request(
        runbook_name="mock.restart_preview",
        parameters={"target": "api", "reason": "演练"},
        requester="operator",
        incident_id=None,
    )

    assert second.id == first.id


def test_forbidden_runbook_is_rejected_before_operation_creation() -> None:
    repository = FakeRunbookRepository()

    with pytest.raises(DataSentryError) as error:
        service(repository).request(
            runbook_name="forbidden.shell_command",
            parameters={"target": "api", "command": "rm -rf /"},
            requester="operator",
            incident_id=None,
        )

    assert error.value.code == "runbook.forbidden"
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
.venv/bin/pytest tests/unit/runbooks/test_service.py -q
```

Expected: FAIL because `RunbookOperationService` is missing.

- [ ] **Step 3: Implement service**

Implement `RunbookOperationService` methods:

- `request(runbook_name, parameters, requester, incident_id=None) -> Operation`
- `approve(operation_id, approver) -> Operation`
- `reject(operation_id, approver) -> Operation`
- `cancel(operation_id, actor) -> Operation`
- `execute(operation_id, actor) -> Operation`
- `events(operation_id) -> list[OperationEvent]`

Rules:

- Request saves the Runbook snapshot, evaluates policy, computes idempotency key, returns active existing Operation when present, otherwise saves a new `AWAITING_APPROVAL` Operation.
- Approve only allows `AWAITING_APPROVAL`.
- Reject only allows `REQUESTED` or `AWAITING_APPROVAL`.
- Execute only allows `APPROVED`.
- Execute acquires lock, marks `RUNNING`, calls executor, marks `VERIFYING`, calls verifier, then marks `SUCCEEDED` or `FAILED`, and releases lock.
- Every state transition writes an `OperationEvent`.

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
.venv/bin/pytest tests/unit/runbooks/test_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/datasentry/runbooks/service.py src/datasentry/runbooks/__init__.py tests/unit/runbooks/test_service.py
git commit -m "feat: 增加Runbook操作服务"
```

---

## Task 6: FastAPI Runbook And Operation Routes

**Files:**
- Modify: `src/datasentry/api/schemas.py`
- Create: `src/datasentry/api/routes/runbooks.py`
- Modify: `src/datasentry/api/routes/operations.py`
- Modify: `src/datasentry/api/dependencies.py`
- Modify: `src/datasentry/api/app.py`
- Test: `tests/integration/api/test_runbooks_api.py`
- Test: `tests/integration/api/test_incidents_evidence_operations.py`

- [ ] **Step 1: Write failing API tests**

Add `tests/integration/api/test_runbooks_api.py`:

```python
from fastapi.testclient import TestClient

from datasentry.api import create_app
from datasentry.config import Settings


def test_runbook_operation_full_api_flow(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATASENTRY_DATABASE_PATH", str(tmp_path / "datasentry.db"))
    client = TestClient(create_app(Settings()))

    runbooks = client.get("/api/runbooks")
    assert runbooks.status_code == 200
    assert runbooks.json()[0]["name"] == "mock.restart_preview"

    created = client.post(
        "/api/operations",
        json={
            "runbook_name": "mock.restart_preview",
            "parameters": {"target": "api", "reason": "演练"},
            "requester": "operator",
        },
    )
    assert created.status_code == 201
    operation_id = created.json()["id"]
    assert created.json()["status"] == "awaiting_approval"

    approved = client.post(f"/api/operations/{operation_id}/approve", json={"approver": "operator"})
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    executed = client.post(f"/api/operations/{operation_id}/execute", json={"actor": "operator"})
    assert executed.status_code == 200
    assert executed.json()["status"] == "succeeded"

    events = client.get(f"/api/operations/{operation_id}/events")
    assert events.status_code == 200
    assert events.json()[-1]["event_type"] == "verification_succeeded"


def test_forbidden_runbook_api_rejects_request(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATASENTRY_DATABASE_PATH", str(tmp_path / "datasentry.db"))
    client = TestClient(create_app(Settings()))

    response = client.post(
        "/api/operations",
        json={
            "runbook_name": "forbidden.shell_command",
            "parameters": {"target": "api", "command": "rm -rf /"},
            "requester": "operator",
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "runbook.forbidden"
```

Update `tests/integration/api/test_incidents_evidence_operations.py::test_operations_simulation_approve_and_reject` expected approved status from `succeeded` to `approved`, then call execute if the test needs success:

```python
assert approved.json()["status"] == "approved"
executed = client.post(f"/api/operations/{operation_id}/execute", json={"actor": "operator"})
assert executed.status_code == 200
assert executed.json()["status"] == "succeeded"
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
.venv/bin/pytest tests/integration/api/test_runbooks_api.py tests/integration/api/test_incidents_evidence_operations.py::test_operations_simulation_approve_and_reject -q
```

Expected: FAIL because routes and schemas are missing or old simulation behavior returns `succeeded` immediately.

- [ ] **Step 3: Implement schemas and dependencies**

Add schemas:

```python
class OperationCreateRequest(BaseModel):
    runbook_name: str = Field(min_length=1)
    parameters: dict[str, object] = Field(default_factory=dict)
    requester: str = Field(min_length=1)
    incident_id: str | None = None


class OperationExecuteRequest(BaseModel):
    actor: str = Field(min_length=1)


class OperationCancelRequest(BaseModel):
    actor: str = Field(min_length=1)
```

Add `get_runbook_catalog()` and `get_runbook_operation_service()` in `src/datasentry/api/dependencies.py`.

- [ ] **Step 4: Implement routes**

Create `src/datasentry/api/routes/runbooks.py` with `GET /runbooks` and `GET /runbooks/{runbook_name}`.

Modify `src/datasentry/api/routes/operations.py`:

- `POST /operations` creates Runbook Operation.
- `POST /operations/simulations` maps legacy names to `mock.restart_preview` or `mock.clear_cache_preview`.
- `POST /operations/{id}/approve` uses M6 service.
- `POST /operations/{id}/reject` uses M6 service.
- `POST /operations/{id}/execute` uses M6 service.
- `POST /operations/{id}/cancel` uses M6 service.
- `GET /operations/{id}/events` returns audit events.

Modify `src/datasentry/api/app.py` to include `runbooks.router`.

- [ ] **Step 5: Run tests to verify GREEN**

Run:

```bash
.venv/bin/pytest tests/integration/api/test_runbooks_api.py tests/integration/api/test_incidents_evidence_operations.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/datasentry/api tests/integration/api
git commit -m "feat: 暴露Runbook审批执行API"
```

---

## Task 7: Frontend Approval Runbook Console

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/ApprovalsPage.tsx`
- Modify: `frontend/src/styles/app.css`

- [ ] **Step 1: Write failing TypeScript surface**

Modify `frontend/src/pages/ApprovalsPage.tsx` first to use new client calls that do not exist yet:

```tsx
const [runbooks, setRunbooks] = useState<Runbook[]>([]);
const [events, setEvents] = useState<OperationEvent[]>([]);
await api.runbooks();
await api.createOperation({ runbook_name, parameters, requester });
await api.executeOperation(operation.id, requester);
await api.operationEvents(operation.id);
```

- [ ] **Step 2: Run typecheck to verify RED**

Run:

```bash
cd frontend && npm run typecheck
```

Expected: FAIL because `Runbook`, `OperationEvent`, and new API client methods are missing.

- [ ] **Step 3: Add frontend types and API client methods**

Add types in `frontend/src/api/types.ts`:

```ts
export type Runbook = {
  name: string;
  version: string;
  title: string;
  description: string;
  risk: string;
  execution_mode: string;
  parameter_schema: Record<string, unknown>;
  enabled: boolean;
  audit_notes: string | null;
};

export type OperationEvent = {
  id: string;
  operation_id: string;
  event_type: string;
  summary: string;
  actor: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type OperationCreatePayload = {
  runbook_name: string;
  parameters: Record<string, unknown>;
  requester: string;
  incident_id?: string | null;
};
```

Extend `Operation` with `version`, `parameters`, `risk`, `incident_id`, `idempotency_key`, `approved_at`, `executed_at`, `verified_at`.

Add client methods in `frontend/src/api/client.ts`:

```ts
runbooks: () => requestJson<Runbook[]>("/api/runbooks"),
createOperation: (payload: OperationCreatePayload) =>
  requestJson<Operation>("/api/operations", { method: "POST", body: JSON.stringify(payload) }),
executeOperation: (operationId: string, actor: string) =>
  requestJson<Operation>(`/api/operations/${operationId}/execute`, {
    method: "POST",
    body: JSON.stringify({ actor })
  }),
cancelOperation: (operationId: string, actor: string) =>
  requestJson<Operation>(`/api/operations/${operationId}/cancel`, {
    method: "POST",
    body: JSON.stringify({ actor })
  }),
operationEvents: (operationId: string) =>
  requestJson<OperationEvent[]>(`/api/operations/${operationId}/events`),
```

- [ ] **Step 4: Implement approval page**

Upgrade `ApprovalsPage` to:

- Load runbooks and operations on mount.
- Provide a runbook select, target input, reason input, requester input.
- Create operation through `/api/operations`.
- Show risk and execution mode.
- Show buttons: approve for `awaiting_approval`, reject for `awaiting_approval`, execute for `approved`, cancel for `requested` or `awaiting_approval`.
- Select an operation row to load audit events.

- [ ] **Step 5: Run typecheck and build to verify GREEN**

Run:

```bash
cd frontend && npm run typecheck
cd frontend && npm run build
```

Expected: both PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/api/client.ts frontend/src/pages/ApprovalsPage.tsx frontend/src/styles/app.css
git commit -m "feat: 升级Runbook审批控制台"
```

---

## Task 8: Documentation And Project Status

**Files:**
- Modify: `README.md`
- Modify: `docs/PROJECT_STATUS.md`
- Test: documentation review with grep/status

- [ ] **Step 1: Update README**

Add an `M6 审批式自动运维` section after the M5 section:

```markdown
## M6 审批式自动运维

M6 第一版只使用 Mock/本地受控执行器，不连接云端实例，不执行 SSH、Shell、数据库写入、Flink Savepoint、补数或生产配置修改。它用于验证 Runbook、审批、审计、幂等、并发锁和操作后验证的工程闭环。

本地启动 API 后，可通过控制台审批页创建 `mock.restart_preview` 或 `mock.clear_cache_preview` Operation。批准后需要显式执行，执行完成后会进入独立 mock 验证，并写入 Operation 审计事件。
```

- [ ] **Step 2: Update project status**

Update `docs/PROJECT_STATUS.md`:

- 当前工作改为 M6 本地受控执行器实现中或已完成。
- 记录不依赖云端实例在线。
- 记录未执行真实生产写操作。
- 添加 M6 实施计划链接 `superpowers/plans/2026-06-28-m6-approval-runbooks.md`。

- [ ] **Step 3: Check docs for unsafe claims**

Run:

```bash
rg -n "自动重启|自动补数|自动 Savepoint|生产写操作已执行|root key" README.md docs/PROJECT_STATUS.md docs/superpowers/specs/2026-06-28-m6-approval-runbooks-design.md docs/superpowers/plans/2026-06-28-m6-approval-runbooks.md
```

Expected: any matches must describe prohibitions or historical risks, not current M6 capability.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/PROJECT_STATUS.md docs/superpowers/plans/2026-06-28-m6-approval-runbooks.md
git commit -m "docs: 记录M6本地审批式运维用法"
```

---

## Task 9: Full Verification And Local API Smoke

**Files:**
- No code changes expected unless verification reveals issues.

- [ ] **Step 1: Run backend quality checks**

Run:

```bash
.venv/bin/ruff format --check .
.venv/bin/ruff check .
.venv/bin/mypy src
.venv/bin/pytest tests -q -W error::ResourceWarning --cov=datasentry --cov-report=term-missing --cov-fail-under=90
```

Expected: all PASS.

- [ ] **Step 2: Run frontend checks**

Run:

```bash
cd frontend && npm run typecheck
cd frontend && npm run build
```

Expected: both PASS.

- [ ] **Step 3: Run FastAPI smoke through TestClient**

Run:

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
from tempfile import TemporaryDirectory
from fastapi.testclient import TestClient

from datasentry.api import create_app
from datasentry.config import Settings

with TemporaryDirectory() as tmp:
    database_path = Path(tmp) / "datasentry.db"
    app = create_app(Settings(database_path=database_path, llm_provider="mock"))
    client = TestClient(app)
    created = client.post(
        "/api/operations",
        json={
            "runbook_name": "mock.restart_preview",
            "parameters": {"target": "api", "reason": "M6 smoke"},
            "requester": "operator",
        },
    )
    created.raise_for_status()
    operation_id = created.json()["id"]
    client.post(f"/api/operations/{operation_id}/approve", json={"approver": "operator"}).raise_for_status()
    executed = client.post(f"/api/operations/{operation_id}/execute", json={"actor": "operator"})
    executed.raise_for_status()
    events = client.get(f"/api/operations/{operation_id}/events")
    events.raise_for_status()
    assert executed.json()["status"] == "succeeded"
    assert events.json()[-1]["event_type"] == "verification_succeeded"
print("M6 API smoke passed")
PY
```

Expected: prints `M6 API smoke passed`.

- [ ] **Step 4: Commit verification fixes if needed**

If verification requires code or docs fixes:

```bash
git add <changed-files>
git commit -m "fix: 修复M6验证问题"
```

- [ ] **Step 5: Record verification in project status**

Update `docs/PROJECT_STATUS.md` with the exact commands and results. Commit:

```bash
git add docs/PROJECT_STATUS.md
git commit -m "docs: 记录M6验证结果"
```

---

## Task 10: Push Branch And Prepare PR

**Files:**
- No code changes.

- [ ] **Step 1: Inspect final diff and log**

Run:

```bash
git status --short --branch
git log --oneline --decorate --max-count=12
git diff origin/main...HEAD --stat
```

Expected: branch is clean and contains only M6 commits.

- [ ] **Step 2: Push branch**

Run:

```bash
git push -u origin codex/m6-approval-runbooks
```

Expected: push succeeds.

- [ ] **Step 3: Create PR**

Run:

```bash
gh pr create \
  --title "feat: 增加M6审批式自动运维本地闭环" \
  --body "## Summary
- add versioned mock Runbooks and Operation audit events
- add approval, execution, idempotency, locks, and mock verification
- upgrade the approval console for M6 local controlled execution

## Verification
- ruff format --check .
- ruff check .
- mypy src
- pytest tests -q -W error::ResourceWarning --cov=datasentry --cov-report=term-missing --cov-fail-under=90
- cd frontend && npm run typecheck
- cd frontend && npm run build
- FastAPI M6 Operation smoke

## Boundary
- no production write operation was executed
- cloud instance was not required for M6 local implementation" \
  --draft
```

Expected: Draft PR URL is created.
