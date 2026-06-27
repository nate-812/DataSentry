# M4 Dialog Web Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the M4 FastAPI Agent, OpenAI-compatible LLM abstraction, React Command Center, evidence views, incident views, and local simulation approval workflow.

**Architecture:** FastAPI owns all production-facing access and exposes JSON plus SSE APIs to the React console. ChatService reuses the existing LiveInspectionService and DiagnosisService, then passes sanitized diagnosis context to an LLM summarizer that can run in disabled, mock, or OpenAI-compatible mode. React renders the Command Center without direct production connectivity; simulated approvals update local SQLite only.

**Tech Stack:** Python 3.12, FastAPI, httpx, Pydantic v2, SQLite, pytest, mypy, Ruff, React, TypeScript, Vite, lucide-react, CSS.

---

## File Structure

Create or modify these files:

- Modify: `pyproject.toml` to add `fastapi` and `uvicorn` runtime dependencies.
- Modify: `src/datasentry/config.py` to add API, CORS, Grafana, and LLM settings.
- Create: `src/datasentry/chat/models.py` for chat session, message, run, run event, and status models.
- Create: `src/datasentry/chat/service.py` for ChatService orchestration.
- Create: `src/datasentry/chat/__init__.py` to export chat models and service.
- Create: `src/datasentry/llm/models.py` for provider messages, options, result, summary, and status enums.
- Create: `src/datasentry/llm/providers.py` for disabled, mock, and OpenAI-compatible providers.
- Create: `src/datasentry/llm/summarizer.py` for deterministic and model-backed answer summaries.
- Create: `src/datasentry/llm/__init__.py` to export LLM interfaces.
- Create: `src/datasentry/operations/simulation.py` for local-only operation approval transitions.
- Create: `src/datasentry/operations/__init__.py`.
- Modify: `src/datasentry/storage/repository.py` to add list and chat persistence methods to the Protocol.
- Modify: `src/datasentry/storage/sqlite.py` to implement list and chat persistence methods.
- Create: `src/datasentry/storage/sql/0003_chat_console.sql` for chat tables.
- Create: `src/datasentry/api/app.py` for FastAPI app creation.
- Create: `src/datasentry/api/dependencies.py` for repository, services, and settings wiring.
- Create: `src/datasentry/api/schemas.py` for public API request and response models.
- Create: `src/datasentry/api/sse.py` for SSE encoding.
- Create: `src/datasentry/api/routes/chat.py`.
- Create: `src/datasentry/api/routes/overview.py`.
- Create: `src/datasentry/api/routes/incidents.py`.
- Create: `src/datasentry/api/routes/operations.py`.
- Create: `src/datasentry/api/routes/alertmanager.py`.
- Create: `src/datasentry/api/routes/evidence.py`.
- Create: `src/datasentry/api/routes/__init__.py`.
- Create: `src/datasentry/api/__init__.py`.
- Modify: `README.md` to document M4 local usage.
- Modify: `docs/PROJECT_STATUS.md` after implementation milestones and final validation.
- Create: `tests/unit/chat/test_models.py`.
- Create: `tests/unit/chat/test_service.py`.
- Create: `tests/unit/llm/test_providers.py`.
- Create: `tests/unit/llm/test_summarizer.py`.
- Create: `tests/unit/operations/test_simulation.py`.
- Modify: `tests/integration/storage/test_sqlite_repository.py`.
- Create: `tests/integration/api/test_health_overview.py`.
- Create: `tests/integration/api/test_chat_api.py`.
- Create: `tests/integration/api/test_incidents_evidence_operations.py`.
- Create: `tests/integration/api/test_alertmanager_api.py`.
- Create: `frontend/package.json`.
- Create: `frontend/tsconfig.json`.
- Create: `frontend/vite.config.ts`.
- Create: `frontend/index.html`.
- Create: `frontend/src/main.tsx`.
- Create: `frontend/src/App.tsx`.
- Create: `frontend/src/api/client.ts`.
- Create: `frontend/src/api/types.ts`.
- Create: `frontend/src/components/Layout.tsx`.
- Create: `frontend/src/components/StatusBadge.tsx`.
- Create: `frontend/src/components/EvidenceList.tsx`.
- Create: `frontend/src/pages/OverviewPage.tsx`.
- Create: `frontend/src/pages/ChatPage.tsx`.
- Create: `frontend/src/pages/IncidentsPage.tsx`.
- Create: `frontend/src/pages/EvidencePage.tsx`.
- Create: `frontend/src/pages/ApprovalsPage.tsx`.
- Create: `frontend/src/pages/GrafanaPage.tsx`.
- Create: `frontend/src/styles/app.css`.

## Planned Public Types

Use these stable names across tasks:

```python
class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"

class ChatRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class ChatEventType(StrEnum):
    ACCEPTED = "accepted"
    KNOWLEDGE_LOADED = "knowledge_loaded"
    TOOLS_PLANNED = "tools_planned"
    TOOL_STARTED = "tool_started"
    TOOL_FINISHED = "tool_finished"
    RULES_COMPLETED = "rules_completed"
    LLM_STARTED = "llm_started"
    LLM_COMPLETED = "llm_completed"
    COMPLETED = "completed"
    FAILED = "failed"

class LLMProviderName(StrEnum):
    DISABLED = "disabled"
    MOCK = "mock"
    OPENAI_COMPATIBLE = "openai_compatible"

class LLMStatus(StrEnum):
    DISABLED = "disabled"
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
```

---

### Task 1: Runtime Dependencies And Settings

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/datasentry/config.py`
- Test: `tests/unit/test_config.py`

- [ ] **Step 1: Write the failing settings test**

Add these tests to `tests/unit/test_config.py`:

```python
def test_m4_llm_settings_default_to_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATASENTRY_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("DATASENTRY_LLM_API_KEY", raising=False)

    settings = Settings()

    assert settings.llm_provider == "disabled"
    assert settings.llm_api_key is None
    assert settings.api_cors_origins == ["http://localhost:5173"]


def test_m4_llm_settings_load_openai_compatible(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATASENTRY_LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("DATASENTRY_LLM_BASE_URL", "https://llm.example.test/v1")
    monkeypatch.setenv("DATASENTRY_LLM_MODEL", "ops-model")
    monkeypatch.setenv("DATASENTRY_LLM_API_KEY", "secret-key")
    monkeypatch.setenv("DATASENTRY_LLM_TIMEOUT_SECONDS", "7")

    settings = Settings()

    assert settings.llm_provider == "openai_compatible"
    assert str(settings.llm_base_url) == "https://llm.example.test/v1"
    assert settings.llm_model == "ops-model"
    assert settings.llm_api_key == "secret-key"
    assert settings.llm_timeout_seconds == 7
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/unit/test_config.py::test_m4_llm_settings_default_to_disabled tests/unit/test_config.py::test_m4_llm_settings_load_openai_compatible -q
```

Expected: FAIL because `Settings` has no `llm_provider`, `llm_api_key`, `llm_base_url`, `llm_model`, `llm_timeout_seconds`, or `api_cors_origins`.

- [ ] **Step 3: Add dependencies and settings**

In `pyproject.toml`, add:

```toml
dependencies = [
  "fastapi>=0.115,<1",
  "httpx>=0.28,<1",
  "paramiko>=3.5,<5",
  "pydantic>=2.11,<3",
  "pydantic-settings>=2.9,<3",
  "PyMySQL>=1.1,<2",
  "redis>=5,<7",
  "structlog>=25.1,<26",
  "typer>=0.16,<1",
  "uvicorn[standard]>=0.34,<1",
]
```

In `src/datasentry/config.py`, add imports and fields:

```python
from pydantic import AnyHttpUrl, Field
```

```python
api_host: str = "127.0.0.1"
api_port: int = 8000
api_cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
grafana_url: AnyHttpUrl | None = None
llm_provider: Literal["disabled", "mock", "openai_compatible"] = "disabled"
llm_base_url: AnyHttpUrl | None = None
llm_model: str | None = None
llm_api_key: str | None = None
llm_timeout_seconds: int = 20
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
pytest tests/unit/test_config.py::test_m4_llm_settings_default_to_disabled tests/unit/test_config.py::test_m4_llm_settings_load_openai_compatible -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/datasentry/config.py tests/unit/test_config.py
git commit -m "feat: 增加M4运行配置"
```

---

### Task 2: Chat Domain Models And SQLite Migration

**Files:**
- Create: `src/datasentry/chat/models.py`
- Create: `src/datasentry/chat/__init__.py`
- Create: `src/datasentry/storage/sql/0003_chat_console.sql`
- Test: `tests/unit/chat/test_models.py`
- Test: `tests/integration/storage/test_migrations.py`

- [ ] **Step 1: Write failing chat model tests**

Create `tests/unit/chat/test_models.py`:

```python
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from datasentry.chat import ChatEventType, ChatMessage, ChatRole, ChatRun, ChatRunStatus, ChatSession

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


def test_chat_run_event_uses_stable_event_type() -> None:
    event = ChatRun.Event(
        run_id="33333333-3333-4333-8333-333333333333",
        event_type=ChatEventType.ACCEPTED,
        payload={"question": "为什么K线不更新"},
        created_at=NOW,
    )

    assert event.event_type is ChatEventType.ACCEPTED
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/unit/chat/test_models.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'datasentry.chat'`.

- [ ] **Step 3: Implement chat models**

Create `src/datasentry/chat/models.py`:

```python
"""对话、诊断任务和 SSE 事件的领域快照模型。"""

from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import Field, JsonValue, field_validator, model_validator

from datasentry.domain.common import DomainModel, new_id, normalize_optional_datetime, require_aware_datetime, utc_now


class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ChatEventType(StrEnum):
    ACCEPTED = "accepted"
    KNOWLEDGE_LOADED = "knowledge_loaded"
    TOOLS_PLANNED = "tools_planned"
    TOOL_STARTED = "tool_started"
    TOOL_FINISHED = "tool_finished"
    RULES_COMPLETED = "rules_completed"
    LLM_STARTED = "llm_started"
    LLM_COMPLETED = "llm_completed"
    COMPLETED = "completed"
    FAILED = "failed"


class ChatSession(DomainModel):
    id: str = Field(default_factory=new_id)
    title: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    _normalize_created_at = field_validator("created_at")(require_aware_datetime)
    _normalize_updated_at = field_validator("updated_at")(require_aware_datetime)

    @model_validator(mode="after")
    def validate_times(self) -> Self:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at 不能早于 created_at")
        return self


class ChatMessage(DomainModel):
    id: str = Field(default_factory=new_id)
    session_id: str = Field(min_length=1)
    role: ChatRole
    content: str = Field(min_length=1)
    inspection_id: str | None = None
    llm_status: str | None = None
    created_at: datetime = Field(default_factory=utc_now)

    _normalize_created_at = field_validator("created_at")(require_aware_datetime)


class ChatRun(DomainModel):
    class Event(DomainModel):
        id: str = Field(default_factory=new_id)
        run_id: str = Field(min_length=1)
        event_type: ChatEventType
        payload: dict[str, JsonValue] = Field(default_factory=dict)
        created_at: datetime = Field(default_factory=utc_now)

        _normalize_created_at = field_validator("created_at")(require_aware_datetime)

    id: str = Field(default_factory=new_id)
    session_id: str = Field(min_length=1)
    user_message_id: str = Field(min_length=1)
    status: ChatRunStatus = ChatRunStatus.RUNNING
    inspection_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None

    _normalize_created_at = field_validator("created_at")(require_aware_datetime)
    _normalize_finished_at = field_validator("finished_at")(normalize_optional_datetime)

    @model_validator(mode="after")
    def validate_run(self) -> Self:
        if self.status is ChatRunStatus.FAILED and (self.error_code is None or self.error_message is None):
            raise ValueError("失败的聊天任务必须包含错误码和错误信息")
        if self.finished_at is not None and self.finished_at < self.created_at:
            raise ValueError("finished_at 不能早于 created_at")
        return self
```

Create `src/datasentry/chat/__init__.py`:

```python
"""对话式 Agent 的领域模型和服务。"""

from datasentry.chat.models import ChatEventType, ChatMessage, ChatRole, ChatRun, ChatRunStatus, ChatSession

__all__ = [
    "ChatEventType",
    "ChatMessage",
    "ChatRole",
    "ChatRun",
    "ChatRunStatus",
    "ChatSession",
]
```

- [ ] **Step 4: Add migration test**

In `tests/integration/storage/test_migrations.py`, add:

```python
def test_upgrade_database_applies_m4_chat_console_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "datasentry.db"

    version = upgrade_database(database_path)

    assert version >= 3
    with connect(database_path) as connection:
        names = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert {"chat_sessions", "chat_messages", "chat_runs", "chat_run_events"} <= names
```

Run:

```bash
pytest tests/integration/storage/test_migrations.py::test_upgrade_database_applies_m4_chat_console_schema -q
```

Expected: FAIL because migration version 3 and chat tables do not exist.

- [ ] **Step 5: Create migration**

Create `src/datasentry/storage/sql/0003_chat_console.sql`:

```sql
CREATE TABLE chat_sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL CHECK (length(trim(title)) > 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE chat_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL CHECK (length(trim(content)) > 0),
    inspection_id TEXT,
    llm_status TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (inspection_id) REFERENCES inspections(id) ON DELETE SET NULL
);

CREATE TABLE chat_runs (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_message_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    inspection_id TEXT,
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    finished_at TEXT,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (user_message_id) REFERENCES chat_messages(id) ON DELETE CASCADE,
    FOREIGN KEY (inspection_id) REFERENCES inspections(id) ON DELETE SET NULL,
    CHECK (
        (status != 'failed' AND error_code IS NULL AND error_message IS NULL)
        OR
        (status = 'failed' AND error_code IS NOT NULL AND error_message IS NOT NULL)
    )
);

CREATE TABLE chat_run_events (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (
        event_type IN (
            'accepted',
            'knowledge_loaded',
            'tools_planned',
            'tool_started',
            'tool_finished',
            'rules_completed',
            'llm_started',
            'llm_completed',
            'completed',
            'failed'
        )
    ),
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES chat_runs(id) ON DELETE CASCADE
);

CREATE INDEX idx_chat_sessions_updated_at
    ON chat_sessions(updated_at);
CREATE INDEX idx_chat_messages_session_created
    ON chat_messages(session_id, created_at);
CREATE INDEX idx_chat_runs_session_created
    ON chat_runs(session_id, created_at);
CREATE INDEX idx_chat_run_events_run_created
    ON chat_run_events(run_id, created_at);
```

- [ ] **Step 6: Run tests to verify they pass**

Run:

```bash
pytest tests/unit/chat/test_models.py tests/integration/storage/test_migrations.py::test_upgrade_database_applies_m4_chat_console_schema -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/datasentry/chat src/datasentry/storage/sql/0003_chat_console.sql tests/unit/chat/test_models.py tests/integration/storage/test_migrations.py
git commit -m "feat: 增加聊天控制台领域模型"
```

---

### Task 3: Repository List And Chat Persistence

**Files:**
- Modify: `src/datasentry/storage/repository.py`
- Modify: `src/datasentry/storage/sqlite.py`
- Test: `tests/integration/storage/test_sqlite_repository.py`

- [ ] **Step 1: Write failing repository tests**

Add tests to `tests/integration/storage/test_sqlite_repository.py`:

```python
from datasentry.chat import ChatEventType, ChatMessage, ChatRole, ChatRun, ChatRunStatus, ChatSession
```

```python
def test_chat_session_message_run_and_event_round_trip(repository: SQLiteRepository) -> None:
    session = ChatSession(
        id="77777777-7777-4777-8777-777777777777",
        title="Kline diagnosis",
        created_at=NOW,
        updated_at=NOW,
    )
    message = ChatMessage(
        id="88888888-8888-4888-8888-888888888888",
        session_id=session.id,
        role=ChatRole.USER,
        content="为什么K线不更新",
        created_at=NOW,
    )
    run = ChatRun(
        id="99999999-9999-4999-8999-999999999999",
        session_id=session.id,
        user_message_id=message.id,
        status=ChatRunStatus.RUNNING,
        created_at=NOW,
    )
    event = ChatRun.Event(
        id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        run_id=run.id,
        event_type=ChatEventType.ACCEPTED,
        payload={"question": "为什么K线不更新"},
        created_at=NOW,
    )

    repository.save_chat_session(session)
    repository.save_chat_message(message)
    repository.save_chat_run(run)
    repository.save_chat_run_event(event)

    assert repository.get_chat_session(session.id) == session
    assert repository.list_chat_sessions(limit=10) == [session]
    assert repository.list_chat_messages(session.id) == [message]
    assert repository.get_chat_run(run.id) == run
    assert repository.list_chat_run_events(run.id) == [event]


def test_list_incidents_and_operations_are_limited(repository: SQLiteRepository) -> None:
    incident = Incident(
        id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        title="Kline delayed",
        symptom="Freshness is behind",
        severity=Severity.WARNING,
        opened_at=NOW,
        updated_at=NOW,
    )
    operation = Operation(
        id="cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        name="simulate_restart_preview",
        version="1",
        risk=OperationRisk.L1,
        requester="operator",
        requested_at=NOW,
    )

    repository.save_incident(incident)
    repository.save_operation(operation)

    assert repository.list_incidents(limit=1) == [incident]
    assert repository.list_operations(limit=1) == [operation]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/integration/storage/test_sqlite_repository.py::test_chat_session_message_run_and_event_round_trip tests/integration/storage/test_sqlite_repository.py::test_list_incidents_and_operations_are_limited -q
```

Expected: FAIL because repository methods are missing.

- [ ] **Step 3: Extend Repository Protocol**

In `src/datasentry/storage/repository.py`, import chat models and add method signatures:

```python
from datasentry.chat import ChatMessage, ChatRun, ChatSession
from datasentry.domain.enums import IncidentStatus, OperationStatus
```

```python
def list_inspections(self, limit: int = 20) -> list[InspectionAggregate]:
    raise NotImplementedError  # pragma: no cover

def list_incidents(
    self,
    *,
    status: IncidentStatus | None = None,
    limit: int = 20,
) -> list[Incident]:
    raise NotImplementedError  # pragma: no cover

def list_operations(
    self,
    *,
    status: OperationStatus | None = None,
    limit: int = 20,
) -> list[Operation]:
    raise NotImplementedError  # pragma: no cover

def save_chat_session(self, session: ChatSession) -> None:
    raise NotImplementedError  # pragma: no cover

def get_chat_session(self, session_id: str) -> ChatSession:
    raise NotImplementedError  # pragma: no cover

def list_chat_sessions(self, limit: int = 20) -> list[ChatSession]:
    raise NotImplementedError  # pragma: no cover

def save_chat_message(self, message: ChatMessage) -> None:
    raise NotImplementedError  # pragma: no cover

def list_chat_messages(self, session_id: str) -> list[ChatMessage]:
    raise NotImplementedError  # pragma: no cover

def save_chat_run(self, run: ChatRun) -> None:
    raise NotImplementedError  # pragma: no cover

def update_chat_run(self, run: ChatRun) -> None:
    raise NotImplementedError  # pragma: no cover

def get_chat_run(self, run_id: str) -> ChatRun:
    raise NotImplementedError  # pragma: no cover

def save_chat_run_event(self, event: ChatRun.Event) -> None:
    raise NotImplementedError  # pragma: no cover

def list_chat_run_events(self, run_id: str) -> list[ChatRun.Event]:
    raise NotImplementedError  # pragma: no cover
```

- [ ] **Step 4: Implement SQLite methods**

In `src/datasentry/storage/sqlite.py`, import:

```python
from datasentry.chat import ChatEventType, ChatMessage, ChatRole, ChatRun, ChatRunStatus, ChatSession
from datasentry.domain.enums import IncidentStatus, OperationStatus
```

Add public methods near existing repository methods:

```python
def list_incidents(self, *, status: IncidentStatus | None = None, limit: int = 20) -> list[Incident]:
    connection = self._require_open()
    if status is None:
        rows = connection.execute(
            "SELECT * FROM incidents ORDER BY updated_at DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    else:
        rows = connection.execute(
            "SELECT * FROM incidents WHERE status = ? ORDER BY updated_at DESC, id DESC LIMIT ?",
            (status.value, limit),
        ).fetchall()
    return [self._row_to_incident(row) for row in rows]

def list_operations(self, *, status: OperationStatus | None = None, limit: int = 20) -> list[Operation]:
    connection = self._require_open()
    if status is None:
        rows = connection.execute(
            "SELECT * FROM operations ORDER BY requested_at DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    else:
        rows = connection.execute(
            "SELECT * FROM operations WHERE status = ? ORDER BY requested_at DESC, id DESC LIMIT ?",
            (status.value, limit),
        ).fetchall()
    return [self._row_to_operation(row) for row in rows]
```

Add chat methods with the same `_dump_datetime`, `_dump_json`, `_load_required_datetime`, and `_load_json` helpers already used in the file. Insert rows with explicit column lists matching `0003_chat_console.sql`. Implement row mappers:

```python
@staticmethod
def _row_to_chat_session(row: sqlite3.Row) -> ChatSession:
    return ChatSession(
        id=row["id"],
        title=row["title"],
        created_at=_load_required_datetime(row["created_at"]),
        updated_at=_load_required_datetime(row["updated_at"]),
    )

@staticmethod
def _row_to_chat_message(row: sqlite3.Row) -> ChatMessage:
    return ChatMessage(
        id=row["id"],
        session_id=row["session_id"],
        role=ChatRole(row["role"]),
        content=row["content"],
        inspection_id=row["inspection_id"],
        llm_status=row["llm_status"],
        created_at=_load_required_datetime(row["created_at"]),
    )

@staticmethod
def _row_to_chat_run(row: sqlite3.Row) -> ChatRun:
    return ChatRun(
        id=row["id"],
        session_id=row["session_id"],
        user_message_id=row["user_message_id"],
        status=ChatRunStatus(row["status"]),
        inspection_id=row["inspection_id"],
        error_code=row["error_code"],
        error_message=row["error_message"],
        created_at=_load_required_datetime(row["created_at"]),
        finished_at=_load_datetime(row["finished_at"]),
    )

@staticmethod
def _row_to_chat_run_event(row: sqlite3.Row) -> ChatRun.Event:
    value = JSON_OBJECT_ADAPTER.validate_python(_load_json(row["payload_json"]))
    return ChatRun.Event(
        id=row["id"],
        run_id=row["run_id"],
        event_type=ChatEventType(row["event_type"]),
        payload=value,
        created_at=_load_required_datetime(row["created_at"]),
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run:

```bash
pytest tests/integration/storage/test_sqlite_repository.py::test_chat_session_message_run_and_event_round_trip tests/integration/storage/test_sqlite_repository.py::test_list_incidents_and_operations_are_limited -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/datasentry/storage/repository.py src/datasentry/storage/sqlite.py tests/integration/storage/test_sqlite_repository.py
git commit -m "feat: 增加控制台持久化查询"
```

---

### Task 4: LLM Providers

**Files:**
- Create: `src/datasentry/llm/models.py`
- Create: `src/datasentry/llm/providers.py`
- Create: `src/datasentry/llm/__init__.py`
- Test: `tests/unit/llm/test_providers.py`

- [ ] **Step 1: Write failing provider tests**

Create `tests/unit/llm/test_providers.py`:

```python
import httpx
import pytest

from datasentry.llm import (
    DisabledLLMProvider,
    LLMMessage,
    LLMOptions,
    LLMProviderError,
    LLMProviderName,
    MockLLMProvider,
    OpenAICompatibleProvider,
)


def test_disabled_provider_reports_disabled_without_network() -> None:
    provider = DisabledLLMProvider()

    result = provider.generate([LLMMessage(role="user", content="hello")], LLMOptions())

    assert result.provider == LLMProviderName.DISABLED
    assert result.status == "disabled"
    assert result.content == ""


def test_mock_provider_returns_stable_text() -> None:
    provider = MockLLMProvider(content="模拟摘要")

    result = provider.generate([LLMMessage(role="user", content="hello")], LLMOptions())

    assert result.provider == LLMProviderName.MOCK
    assert result.status == "available"
    assert result.content == "模拟摘要"


def test_openai_compatible_provider_sends_authorization_header() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "模型摘要"}}]},
        )

    provider = OpenAICompatibleProvider(
        base_url="https://llm.example.test/v1",
        api_key="secret-key",
        model="ops-model",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = provider.generate([LLMMessage(role="user", content="hello")], LLMOptions())

    assert result.content == "模型摘要"
    assert requests[0].headers["authorization"] == "Bearer secret-key"


def test_openai_compatible_provider_redacts_api_key_in_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "secret-key rejected"}})

    provider = OpenAICompatibleProvider(
        base_url="https://llm.example.test/v1",
        api_key="secret-key",
        model="ops-model",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(LLMProviderError) as raised:
        provider.generate([LLMMessage(role="user", content="hello")], LLMOptions())

    assert raised.value.code == "llm.authentication_failed"
    assert "secret-key" not in raised.value.message
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/unit/llm/test_providers.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'datasentry.llm'`.

- [ ] **Step 3: Implement provider models and errors**

Create `src/datasentry/llm/models.py`:

```python
"""LLM Provider 的稳定输入输出模型。"""

from enum import StrEnum

from pydantic import Field

from datasentry.domain.common import DomainModel


class LLMProviderName(StrEnum):
    DISABLED = "disabled"
    MOCK = "mock"
    OPENAI_COMPATIBLE = "openai_compatible"


class LLMStatus(StrEnum):
    DISABLED = "disabled"
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class LLMMessage(DomainModel):
    role: str = Field(min_length=1)
    content: str = Field(min_length=1)


class LLMOptions(DomainModel):
    temperature: float = 0.2
    max_tokens: int = 800


class LLMResult(DomainModel):
    provider: LLMProviderName
    status: LLMStatus
    content: str
```

- [ ] **Step 4: Implement providers**

Create `src/datasentry/llm/providers.py` with:

```python
"""可插拔 LLM Provider。"""

from typing import Protocol

import httpx

from datasentry.errors import DataSentryError
from datasentry.llm.models import LLMMessage, LLMOptions, LLMProviderName, LLMResult, LLMStatus


class LLMProviderError(DataSentryError):
    """LLM 调用失败，错误信息已脱敏。"""


class LLMProvider(Protocol):
    def generate(self, messages: list[LLMMessage], options: LLMOptions) -> LLMResult:
        raise NotImplementedError  # pragma: no cover


class DisabledLLMProvider:
    def generate(self, messages: list[LLMMessage], options: LLMOptions) -> LLMResult:
        del messages, options
        return LLMResult(
            provider=LLMProviderName.DISABLED,
            status=LLMStatus.DISABLED,
            content="",
        )


class MockLLMProvider:
    def __init__(self, content: str = "这是模拟 LLM 摘要。") -> None:
        self._content = content

    def generate(self, messages: list[LLMMessage], options: LLMOptions) -> LLMResult:
        del messages, options
        return LLMResult(
            provider=LLMProviderName.MOCK,
            status=LLMStatus.AVAILABLE,
            content=self._content,
        )


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        client: httpx.Client | None = None,
        timeout_seconds: int = 20,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def generate(self, messages: list[LLMMessage], options: LLMOptions) -> LLMResult:
        payload = {
            "model": self._model,
            "messages": [message.model_dump(mode="json") for message in messages],
            "temperature": options.temperature,
            "max_tokens": options.max_tokens,
        }
        try:
            response = self._client.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
            )
        except httpx.TimeoutException as error:
            raise LLMProviderError(
                code="llm.timeout",
                message="LLM 调用超时",
            ) from error
        except httpx.HTTPError as error:
            raise LLMProviderError(
                code="llm.upstream_error",
                message="LLM 上游调用失败",
            ) from error
        if response.status_code in {401, 403}:
            raise LLMProviderError(
                code="llm.authentication_failed",
                message="LLM 认证失败",
            )
        if response.status_code >= 400:
            raise LLMProviderError(
                code="llm.upstream_error",
                message="LLM 上游返回错误",
            )
        data = response.json()
        content = str(data["choices"][0]["message"]["content"])
        return LLMResult(
            provider=LLMProviderName.OPENAI_COMPATIBLE,
            status=LLMStatus.AVAILABLE,
            content=content,
        )
```

Create `src/datasentry/llm/__init__.py` exporting all public names.

- [ ] **Step 5: Run tests to verify they pass**

Run:

```bash
pytest tests/unit/llm/test_providers.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/datasentry/llm tests/unit/llm/test_providers.py
git commit -m "feat: 增加可插拔LLM提供方"
```

---

### Task 5: Answer Summarizer

**Files:**
- Create: `src/datasentry/llm/summarizer.py`
- Modify: `src/datasentry/llm/__init__.py`
- Test: `tests/unit/llm/test_summarizer.py`

- [ ] **Step 1: Write failing summarizer tests**

Create `tests/unit/llm/test_summarizer.py`:

```python
from datetime import UTC, datetime

from datasentry.domain import EvidenceStatus, Finding, Severity
from datasentry.llm import AnswerContext, AnswerSummarizer, DisabledLLMProvider, MockLLMProvider

NOW = datetime(2026, 6, 27, 8, 0, tzinfo=UTC)


def _finding() -> Finding:
    return Finding(
        inspection_id="11111111-1111-4111-8111-111111111111",
        severity=Severity.WARNING,
        status=EvidenceStatus.CONFIRMED,
        claim="Kline 数据在 Flink 之后停止推进",
        evidence=[],
        impact="前端可能看到旧数据",
        recommendation="检查 Flink Kline Job 和 Doris 新鲜度",
        unknowns=["Spring API 返回空数组的原因仍需确认"],
        created_at=NOW,
    )


def test_summarizer_uses_deterministic_template_when_llm_disabled() -> None:
    summarizer = AnswerSummarizer(provider=DisabledLLMProvider())

    summary = summarizer.summarize(
        AnswerContext(
            question="为什么K线不更新",
            findings=[_finding()],
            tool_invocation_count=3,
        )
    )

    assert summary.llm_status == "disabled"
    assert "当前结论" in summary.content
    assert "Kline 数据在 Flink 之后停止推进" in summary.content


def test_summarizer_uses_model_content_when_available() -> None:
    summarizer = AnswerSummarizer(provider=MockLLMProvider(content="模型整理后的回答"))

    summary = summarizer.summarize(
        AnswerContext(
            question="为什么K线不更新",
            findings=[_finding()],
            tool_invocation_count=3,
        )
    )

    assert summary.llm_status == "available"
    assert summary.content == "模型整理后的回答"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/unit/llm/test_summarizer.py -q
```

Expected: FAIL because `AnswerContext` and `AnswerSummarizer` are missing.

- [ ] **Step 3: Implement summarizer**

Create `src/datasentry/llm/summarizer.py`:

```python
"""将确定性诊断结果整理成面向用户的中文回答。"""

from pydantic import Field

from datasentry.domain import Finding
from datasentry.domain.common import DomainModel
from datasentry.llm.models import LLMMessage, LLMOptions
from datasentry.llm.providers import LLMProvider, LLMProviderError


class AnswerContext(DomainModel):
    question: str = Field(min_length=1)
    findings: list[Finding] = Field(default_factory=list)
    tool_invocation_count: int = 0


class AnswerSummary(DomainModel):
    content: str
    llm_status: str


class AnswerSummarizer:
    def __init__(self, *, provider: LLMProvider) -> None:
        self._provider = provider

    def summarize(self, context: AnswerContext) -> AnswerSummary:
        deterministic = self._deterministic_summary(context)
        result = self._provider.generate(
            [
                LLMMessage(
                    role="system",
                    content=(
                        "你是 DataSentry 运维 Agent。只能基于给定证据回答，"
                        "不得编造事实，不得生成 Shell、SQL 或 Redis 写命令。"
                    ),
                ),
                LLMMessage(role="user", content=deterministic),
            ],
            LLMOptions(),
        )
        if result.status == "available" and result.content.strip():
            return AnswerSummary(content=result.content.strip(), llm_status=result.status.value)
        return AnswerSummary(content=deterministic, llm_status=result.status.value)

    @staticmethod
    def _deterministic_summary(context: AnswerContext) -> str:
        if context.findings:
            finding = context.findings[0]
            unknowns = "；".join(finding.unknowns) if finding.unknowns else "暂无"
            return (
                f"当前结论：{finding.claim}\n"
                f"已确认事实：已完成 {context.tool_invocation_count} 次只读工具调用。\n"
                f"推断：{finding.impact}\n"
                f"未知项：{unknowns}\n"
                f"建议下一步：{finding.recommendation}"
            )
        return (
            "当前结论：证据不足，尚不能确认根因。\n"
            f"已确认事实：已完成 {context.tool_invocation_count} 次只读工具调用。\n"
            "推断：暂无。\n未知项：缺少可判定的 Finding。\n建议下一步：继续收集现场证据。"
        )
```

Wrap `provider.generate` with `try/except LLMProviderError` and return deterministic content with `llm_status="unavailable"` when provider raises.

- [ ] **Step 4: Export summarizer names**

Update `src/datasentry/llm/__init__.py`:

```python
from datasentry.llm.summarizer import AnswerContext, AnswerSummarizer, AnswerSummary
```

Add these names to `__all__`.

- [ ] **Step 5: Run tests to verify they pass**

Run:

```bash
pytest tests/unit/llm/test_summarizer.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/datasentry/llm tests/unit/llm/test_summarizer.py
git commit -m "feat: 增加诊断回答摘要器"
```

---

### Task 6: Local Simulation Operation Service

**Files:**
- Create: `src/datasentry/operations/simulation.py`
- Create: `src/datasentry/operations/__init__.py`
- Test: `tests/unit/operations/test_simulation.py`

- [ ] **Step 1: Write failing simulation tests**

Create `tests/unit/operations/test_simulation.py`:

```python
from datetime import UTC, datetime

import pytest

from datasentry.domain import Operation, OperationRisk, OperationStatus
from datasentry.errors import DataSentryError
from datasentry.operations import SimulationOperationService

NOW = datetime(2026, 6, 27, 8, 0, tzinfo=UTC)


class MemoryOperationRepository:
    def __init__(self, operation: Operation) -> None:
        self.operation = operation

    def get_operation(self, operation_id: str) -> Operation:
        assert operation_id == self.operation.id
        return self.operation

    def update_operation(self, operation: Operation) -> None:
        self.operation = operation


def test_approve_simulation_operation_succeeds() -> None:
    operation = Operation(
        id="11111111-1111-4111-8111-111111111111",
        name="simulate_restart_preview",
        version="1",
        risk=OperationRisk.L1,
        requester="operator",
        requested_at=NOW,
    )
    repository = MemoryOperationRepository(operation)
    service = SimulationOperationService(repository=repository, clock=lambda: NOW)

    updated = service.approve(operation.id, approver="operator")

    assert updated.status is OperationStatus.SUCCEEDED
    assert updated.result == {"simulation": True, "status": "succeeded"}


def test_reject_non_simulation_operation_is_denied() -> None:
    operation = Operation(
        id="11111111-1111-4111-8111-111111111111",
        name="restart_flink",
        version="1",
        risk=OperationRisk.L2,
        requester="operator",
        requested_at=NOW,
    )
    service = SimulationOperationService(
        repository=MemoryOperationRepository(operation),
        clock=lambda: NOW,
    )

    with pytest.raises(DataSentryError) as raised:
        service.approve(operation.id, approver="operator")

    assert raised.value.code == "operation.not_simulation"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/unit/operations/test_simulation.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'datasentry.operations'`.

- [ ] **Step 3: Implement simulation service**

Create `src/datasentry/operations/simulation.py`:

```python
"""本地模拟审批流，不执行生产 Runbook。"""

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from datasentry.domain import Operation, OperationStatus
from datasentry.domain.common import utc_now
from datasentry.errors import DataSentryError


class OperationRepository(Protocol):
    def get_operation(self, operation_id: str) -> Operation:
        raise NotImplementedError  # pragma: no cover

    def update_operation(self, operation: Operation) -> None:
        raise NotImplementedError  # pragma: no cover


class SimulationOperationService:
    def __init__(
        self,
        *,
        repository: OperationRepository,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._repository = repository
        self._clock = clock

    def approve(self, operation_id: str, *, approver: str) -> Operation:
        operation = self._get_simulation_operation(operation_id)
        now = self._clock()
        updated = operation.model_copy(
            update={
                "status": OperationStatus.SUCCEEDED,
                "approver": approver,
                "approved_at": now,
                "executed_at": now,
                "verified_at": now,
                "result": {"simulation": True, "status": "succeeded"},
            }
        )
        self._repository.update_operation(updated)
        return updated

    def reject(self, operation_id: str, *, approver: str) -> Operation:
        operation = self._get_simulation_operation(operation_id)
        now = self._clock()
        updated = operation.model_copy(
            update={
                "status": OperationStatus.REJECTED,
                "approver": approver,
                "approved_at": now,
                "result": {"simulation": True, "status": "rejected"},
            }
        )
        self._repository.update_operation(updated)
        return updated

    def _get_simulation_operation(self, operation_id: str) -> Operation:
        operation = self._repository.get_operation(operation_id)
        if not operation.name.startswith("simulate_"):
            raise DataSentryError(
                code="operation.not_simulation",
                message="M4 只允许处理本地模拟审批操作",
            )
        return operation
```

Create `src/datasentry/operations/__init__.py` exporting `SimulationOperationService`.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
pytest tests/unit/operations/test_simulation.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/datasentry/operations tests/unit/operations/test_simulation.py
git commit -m "feat: 增加本地模拟审批服务"
```

---

### Task 7: ChatService And Event Recording

**Files:**
- Create: `src/datasentry/chat/service.py`
- Modify: `src/datasentry/chat/__init__.py`
- Test: `tests/unit/chat/test_service.py`

- [ ] **Step 1: Write failing ChatService tests**

Create `tests/unit/chat/test_service.py`:

```python
from datetime import UTC, datetime

from datasentry.chat import ChatEventType, ChatRole, ChatService
from datasentry.domain import Finding, Inspection, InspectionStatus, Severity, EvidenceStatus
from datasentry.llm import AnswerSummary
from datasentry.storage import InspectionAggregate
from datasentry.tools import LiveInspectionResult

NOW = datetime(2026, 6, 27, 8, 0, tzinfo=UTC)


class FakeRepository:
    def __init__(self) -> None:
        self.sessions = []
        self.messages = []
        self.runs = []
        self.events = []

    def save_chat_session(self, session): self.sessions.append(session)
    def save_chat_message(self, message): self.messages.append(message)
    def save_chat_run(self, run): self.runs.append(run)
    def update_chat_run(self, run): self.runs.append(run)
    def save_chat_run_event(self, event): self.events.append(event)


class FakeLiveInspectionService:
    def run(self, question: str) -> LiveInspectionResult:
        inspection = Inspection(
            question=question,
            status=InspectionStatus.COMPLETED,
            summary="Kline delayed",
            started_at=NOW,
            finished_at=NOW,
        )
        finding = Finding(
            inspection_id=inspection.id,
            severity=Severity.WARNING,
            status=EvidenceStatus.CONFIRMED,
            claim="Kline 数据停止推进",
            evidence=[],
            impact="页面可能显示旧数据",
            recommendation="检查 Flink Job",
            unknowns=[],
            created_at=NOW,
        )
        return LiveInspectionResult(
            diagnosis=type(
                "Diagnosis",
                (),
                {"aggregate": InspectionAggregate(inspection, [], [finding])},
            )(),
            tool_invocations=[],
        )


class FakeSummarizer:
    def summarize(self, context):
        return AnswerSummary(content="当前结论：Kline 数据停止推进", llm_status="disabled")


def test_chat_service_records_user_assistant_run_and_events() -> None:
    repository = FakeRepository()
    service = ChatService(
        repository=repository,
        live_inspection=FakeLiveInspectionService(),
        summarizer=FakeSummarizer(),
        clock=lambda: NOW,
    )

    session = service.create_session(title="Kline")
    result = service.run_question(session.id, "为什么K线不更新")

    assert result.assistant_message.role is ChatRole.ASSISTANT
    assert result.assistant_message.content.startswith("当前结论")
    assert [event.event_type for event in repository.events] == [
        ChatEventType.ACCEPTED,
        ChatEventType.TOOLS_PLANNED,
        ChatEventType.RULES_COMPLETED,
        ChatEventType.LLM_STARTED,
        ChatEventType.LLM_COMPLETED,
        ChatEventType.COMPLETED,
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/unit/chat/test_service.py -q
```

Expected: FAIL because `ChatService` is missing.

- [ ] **Step 3: Implement ChatService**

Create `src/datasentry/chat/service.py` with:

```python
"""对话诊断编排服务。"""

from collections.abc import Callable
from datetime import datetime

from pydantic import Field

from datasentry.chat.models import ChatEventType, ChatMessage, ChatRole, ChatRun, ChatRunStatus, ChatSession
from datasentry.domain.common import DomainModel, utc_now
from datasentry.errors import DataSentryError
from datasentry.llm import AnswerContext, AnswerSummarizer
from datasentry.storage import Repository
from datasentry.tools import LiveInspectionService


class ChatRunResult(DomainModel):
    run: ChatRun
    user_message: ChatMessage
    assistant_message: ChatMessage
    event_count: int = Field(ge=0)


class ChatService:
    def __init__(
        self,
        *,
        repository: Repository,
        live_inspection: LiveInspectionService,
        summarizer: AnswerSummarizer,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._repository = repository
        self._live_inspection = live_inspection
        self._summarizer = summarizer
        self._clock = clock

    def create_session(self, *, title: str) -> ChatSession:
        now = self._clock()
        session = ChatSession(title=title, created_at=now, updated_at=now)
        self._repository.save_chat_session(session)
        return session

    def run_question(self, session_id: str, question: str) -> ChatRunResult:
        now = self._clock()
        user_message = ChatMessage(session_id=session_id, role=ChatRole.USER, content=question, created_at=now)
        self._repository.save_chat_message(user_message)
        run = ChatRun(session_id=session_id, user_message_id=user_message.id, created_at=now)
        self._repository.save_chat_run(run)
        event_count = 0

        def emit(event_type: ChatEventType, payload: dict[str, object]) -> None:
            nonlocal event_count
            self._repository.save_chat_run_event(
                ChatRun.Event(run_id=run.id, event_type=event_type, payload=payload, created_at=self._clock())
            )
            event_count += 1

        try:
            emit(ChatEventType.ACCEPTED, {"question": question})
            emit(ChatEventType.TOOLS_PLANNED, {"source": "live_inspection_service"})
            live_result = self._live_inspection.run(question)
            aggregate = live_result.diagnosis.aggregate
            emit(ChatEventType.RULES_COMPLETED, {"finding_count": len(aggregate.findings)})
            emit(ChatEventType.LLM_STARTED, {"provider": "configured"})
            summary = self._summarizer.summarize(
                AnswerContext(
                    question=question,
                    findings=aggregate.findings,
                    tool_invocation_count=len(live_result.tool_invocations),
                )
            )
            emit(ChatEventType.LLM_COMPLETED, {"llm_status": summary.llm_status})
            assistant_message = ChatMessage(
                session_id=session_id,
                role=ChatRole.ASSISTANT,
                content=summary.content,
                inspection_id=aggregate.inspection.id,
                llm_status=summary.llm_status,
                created_at=self._clock(),
            )
            self._repository.save_chat_message(assistant_message)
            completed = run.model_copy(
                update={
                    "status": ChatRunStatus.COMPLETED,
                    "inspection_id": aggregate.inspection.id,
                    "finished_at": self._clock(),
                }
            )
            self._repository.update_chat_run(completed)
            emit(ChatEventType.COMPLETED, {"inspection_id": aggregate.inspection.id})
            return ChatRunResult(
                run=completed,
                user_message=user_message,
                assistant_message=assistant_message,
                event_count=event_count,
            )
        except Exception as error:
            failed = run.model_copy(
                update={
                    "status": ChatRunStatus.FAILED,
                    "error_code": getattr(error, "code", "internal.error"),
                    "error_message": "对话诊断失败",
                    "finished_at": self._clock(),
                }
            )
            self._repository.update_chat_run(failed)
            emit(ChatEventType.FAILED, {"code": failed.error_code, "message": failed.error_message})
            if isinstance(error, DataSentryError):
                raise
            raise
```

Update `src/datasentry/chat/__init__.py` to export `ChatRunResult` and `ChatService`.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
pytest tests/unit/chat/test_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/datasentry/chat tests/unit/chat/test_service.py
git commit -m "feat: 增加对话诊断服务"
```

---

### Task 8: FastAPI App, Schemas, Health, Overview, Evidence, Incidents, Operations

**Files:**
- Create: `src/datasentry/api/app.py`
- Create: `src/datasentry/api/dependencies.py`
- Create: `src/datasentry/api/schemas.py`
- Create: `src/datasentry/api/sse.py`
- Create: `src/datasentry/api/routes/overview.py`
- Create: `src/datasentry/api/routes/incidents.py`
- Create: `src/datasentry/api/routes/operations.py`
- Create: `src/datasentry/api/routes/evidence.py`
- Create: `src/datasentry/api/routes/__init__.py`
- Create: `src/datasentry/api/__init__.py`
- Test: `tests/integration/api/test_health_overview.py`
- Test: `tests/integration/api/test_incidents_evidence_operations.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/integration/api/test_health_overview.py`:

```python
from fastapi.testclient import TestClient

from datasentry.api import create_app
from datasentry.config import Settings


def test_health_does_not_expose_llm_api_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATASENTRY_DATABASE_PATH", str(tmp_path / "datasentry.db"))
    monkeypatch.setenv("DATASENTRY_LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("DATASENTRY_LLM_API_KEY", "secret-key")
    app = create_app(Settings())

    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["llm"]["provider"] == "openai_compatible"
    assert "secret-key" not in response.text


def test_overview_returns_command_center_sections(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATASENTRY_DATABASE_PATH", str(tmp_path / "datasentry.db"))
    app = create_app(Settings())

    response = TestClient(app).get("/api/overview")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) >= {"health", "recent_inspections", "incidents", "operations", "grafana"}
```

Create `tests/integration/api/test_incidents_evidence_operations.py` with tests for:

```python
def test_operations_simulation_approve_and_reject(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATASENTRY_DATABASE_PATH", str(tmp_path / "datasentry.db"))
    app = create_app(Settings())
    client = TestClient(app)

    created = client.post(
        "/api/operations/simulations",
        json={"name": "simulate_restart_preview", "requester": "operator"},
    )
    assert created.status_code == 201
    operation_id = created.json()["id"]

    approved = client.post(f"/api/operations/{operation_id}/approve", json={"approver": "operator"})

    assert approved.status_code == 200
    assert approved.json()["status"] == "succeeded"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/integration/api/test_health_overview.py tests/integration/api/test_incidents_evidence_operations.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'datasentry.api'`.

- [ ] **Step 3: Implement FastAPI app and schemas**

Create `src/datasentry/api/app.py`:

```python
"""DataSentry M4 FastAPI 应用。"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from datasentry.api.routes import evidence, incidents, operations, overview
from datasentry.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or Settings()
    app = FastAPI(title="DataSentry API", version="0.1.0")
    app.state.settings = resolved
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.api_cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.include_router(overview.router, prefix="/api")
    app.include_router(evidence.router, prefix="/api")
    app.include_router(incidents.router, prefix="/api")
    app.include_router(operations.router, prefix="/api")
    return app
```

Create dependencies that open `SQLiteRepository(settings.database_path)` per request and close it in a `finally` block. Create schemas with Pydantic models for health, overview, operation simulation request, and operation action request.

- [ ] **Step 4: Implement health and overview routes**

`GET /api/health` returns:

```json
{
  "status": "ok",
  "environment": "development",
  "database": {"configured": true},
  "llm": {"provider": "disabled", "configured": true}
}
```

`GET /api/overview` returns:

```json
{
  "health": {"status": "ok"},
  "recent_inspections": [],
  "incidents": [],
  "operations": [],
  "grafana": {"url": null}
}
```

- [ ] **Step 5: Implement incidents, evidence, and operations routes**

Use Repository methods from Task 3 and `SimulationOperationService` from Task 6. Simulation creation constructs:

```python
Operation(
    name=request.name,
    version="m4-simulation",
    risk=OperationRisk.L1,
    requester=request.requester,
)
```

Reject `name` values that do not start with `simulate_` with `DataSentryError(code="operation.not_simulation", message="M4 只允许创建本地模拟审批操作")`.

- [ ] **Step 6: Export app factory**

Create `src/datasentry/api/__init__.py`:

```python
"""DataSentry FastAPI 应用入口。"""

from datasentry.api.app import create_app

__all__ = ["create_app"]
```

- [ ] **Step 7: Run tests to verify they pass**

Run:

```bash
pytest tests/integration/api/test_health_overview.py tests/integration/api/test_incidents_evidence_operations.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/datasentry/api tests/integration/api/test_health_overview.py tests/integration/api/test_incidents_evidence_operations.py
git commit -m "feat: 增加M4基础API"
```

---

### Task 9: Chat API And SSE Replay

**Files:**
- Create: `src/datasentry/api/routes/chat.py`
- Modify: `src/datasentry/api/app.py`
- Modify: `src/datasentry/api/dependencies.py`
- Test: `tests/integration/api/test_chat_api.py`

- [ ] **Step 1: Write failing chat API tests**

Create `tests/integration/api/test_chat_api.py`:

```python
from fastapi.testclient import TestClient

from datasentry.api import create_app
from datasentry.config import Settings


def test_chat_session_lifecycle_with_mock_llm(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATASENTRY_DATABASE_PATH", str(tmp_path / "datasentry.db"))
    monkeypatch.setenv("DATASENTRY_TARGETS_FILE", "config/targets.example.toml")
    monkeypatch.setenv("DATASENTRY_LLM_PROVIDER", "mock")
    app = create_app(Settings())
    client = TestClient(app)

    session_response = client.post("/api/chat/sessions", json={"title": "Kline"})
    assert session_response.status_code == 201
    session_id = session_response.json()["id"]

    run_response = client.post(
        f"/api/chat/sessions/{session_id}/runs",
        json={"question": "为什么K线不更新"},
    )

    assert run_response.status_code in {200, 201}
    payload = run_response.json()
    assert payload["assistant_message"]["role"] == "assistant"
    assert payload["run"]["status"] in {"completed", "failed"}


def test_chat_run_events_are_returned_as_sse(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATASENTRY_DATABASE_PATH", str(tmp_path / "datasentry.db"))
    monkeypatch.setenv("DATASENTRY_TARGETS_FILE", "config/targets.example.toml")
    app = create_app(Settings())
    client = TestClient(app)
    session_id = client.post("/api/chat/sessions", json={"title": "Kline"}).json()["id"]
    run_id = client.post(
        f"/api/chat/sessions/{session_id}/runs",
        json={"question": "为什么K线不更新"},
    ).json()["run"]["id"]

    response = client.get(f"/api/chat/runs/{run_id}/events")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: accepted" in response.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/integration/api/test_chat_api.py -q
```

Expected: FAIL because chat routes are not mounted.

- [ ] **Step 3: Wire ChatService dependencies**

In `src/datasentry/api/dependencies.py`, add factories:

```python
def build_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "mock":
        return MockLLMProvider()
    if settings.llm_provider == "openai_compatible":
        if settings.llm_base_url is None or settings.llm_model is None or settings.llm_api_key is None:
            return DisabledLLMProvider()
        return OpenAICompatibleProvider(
            base_url=str(settings.llm_base_url),
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    return DisabledLLMProvider()
```

Build `LiveInspectionService` with existing `build_live_inspection_service(repository, targets, knowledge_root)` and `TargetCatalog.load(settings.targets_file)`.

- [ ] **Step 4: Implement chat routes**

Create routes:

```text
POST /api/chat/sessions
GET /api/chat/sessions
GET /api/chat/sessions/{session_id}
POST /api/chat/sessions/{session_id}/runs
GET /api/chat/runs/{run_id}
GET /api/chat/runs/{run_id}/events
```

For M4, `/runs` can execute synchronously and persist ordered events; `/events` streams saved events. Encode events with:

```python
def encode_sse(event: str, data: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
```

- [ ] **Step 5: Mount chat router**

Update `create_app`:

```python
from datasentry.api.routes import chat, evidence, incidents, operations, overview
app.include_router(chat.router, prefix="/api")
```

- [ ] **Step 6: Run tests to verify they pass**

Run:

```bash
pytest tests/integration/api/test_chat_api.py -q
```

Expected: PASS. If example target configuration lacks secrets, the route may return a failed run; the API contract still returns assistant or failure-safe run JSON and event stream.

- [ ] **Step 7: Commit**

```bash
git add src/datasentry/api tests/integration/api/test_chat_api.py
git commit -m "feat: 增加对话诊断API"
```

---

### Task 10: Alertmanager Webhook API

**Files:**
- Create: `src/datasentry/api/routes/alertmanager.py`
- Modify: `src/datasentry/api/app.py`
- Test: `tests/integration/api/test_alertmanager_api.py`

- [ ] **Step 1: Write failing Alertmanager API test**

Create `tests/integration/api/test_alertmanager_api.py`:

```python
import json
from pathlib import Path

from fastapi.testclient import TestClient

from datasentry.api import create_app
from datasentry.config import Settings


def test_alertmanager_webhook_parses_payload(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATASENTRY_DATABASE_PATH", str(tmp_path / "datasentry.db"))
    payload = json.loads(Path("tests/fixtures/alertmanager/kline_freshness_firing.json").read_text())
    client = TestClient(create_app(Settings()))

    response = client.post("/api/alertmanager/webhook", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "accepted"
    assert body["alert_count"] >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/integration/api/test_alertmanager_api.py -q
```

Expected: FAIL because route is missing.

- [ ] **Step 3: Implement route**

Create `src/datasentry/api/routes/alertmanager.py`:

```python
"""Alertmanager Webhook API。"""

from typing import Any

from fastapi import APIRouter

from datasentry.notifications import parse_alertmanager_payload

router = APIRouter(tags=["alertmanager"])


@router.post("/alertmanager/webhook")
def receive_alertmanager_webhook(payload: dict[str, Any]) -> dict[str, object]:
    parsed = parse_alertmanager_payload(payload)
    return {
        "status": "accepted",
        "alert_count": len(parsed.alerts),
        "group_key": parsed.group_key,
    }
```

Mount it in `create_app`.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
pytest tests/integration/api/test_alertmanager_api.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/datasentry/api/routes/alertmanager.py src/datasentry/api/app.py tests/integration/api/test_alertmanager_api.py
git commit -m "feat: 增加Alertmanager API入口"
```

---

### Task 11: Frontend Scaffold And API Client

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/index.html`
- Create: `frontend/src/api/types.ts`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/styles/app.css`

- [ ] **Step 1: Create frontend package**

Create `frontend/package.json`:

```json
{
  "name": "datasentry-console",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite --host 127.0.0.1",
    "build": "tsc -b && vite build",
    "typecheck": "tsc -b"
  },
  "dependencies": {
    "@vitejs/plugin-react": "^4.3.4",
    "lucide-react": "^0.468.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "vite": "^6.0.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.17",
    "@types/react-dom": "^18.3.5",
    "typescript": "^5.7.2"
  }
}
```

Create `tsconfig.json`, `vite.config.ts`, `index.html`, and minimal `src/main.tsx` rendering `<App />`.

- [ ] **Step 2: Create API types**

Create `frontend/src/api/types.ts`:

```typescript
export type HealthResponse = {
  status: string;
  environment: string;
  database: { configured: boolean };
  llm: { provider: string; configured: boolean };
};

export type OverviewResponse = {
  health: { status: string };
  recent_inspections: unknown[];
  incidents: unknown[];
  operations: unknown[];
  grafana: { url: string | null };
};

export type ChatSession = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
};

export type ChatRunResponse = {
  run: { id: string; status: string; inspection_id: string | null };
  assistant_message: {
    id: string;
    role: "assistant";
    content: string;
    inspection_id: string | null;
    llm_status: string | null;
  };
};
```

- [ ] **Step 3: Create API client**

Create `frontend/src/api/client.ts`:

```typescript
import type { ChatRunResponse, ChatSession, HealthResponse, OverviewResponse } from "./types";

const API_BASE = import.meta.env.VITE_DATASENTRY_API_BASE ?? "http://127.0.0.1:8000";

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    throw new Error(`DataSentry API error ${response.status}`);
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => requestJson<HealthResponse>("/api/health"),
  overview: () => requestJson<OverviewResponse>("/api/overview"),
  createSession: (title: string) =>
    requestJson<ChatSession>("/api/chat/sessions", {
      method: "POST",
      body: JSON.stringify({ title }),
    }),
  runQuestion: (sessionId: string, question: string) =>
    requestJson<ChatRunResponse>(`/api/chat/sessions/${sessionId}/runs`, {
      method: "POST",
      body: JSON.stringify({ question }),
    }),
};
```

- [ ] **Step 4: Create minimal App**

Create `frontend/src/App.tsx` that imports `api`, fetches health and overview on mount, and renders Command Center shell with Chinese UI text. Use lucide-react icons such as `Activity`, `MessageSquare`, `ShieldCheck`, `ExternalLink`.

- [ ] **Step 5: Install dependencies**

Run:

```bash
cd frontend
npm install
```

Expected: creates `frontend/package-lock.json`.

- [ ] **Step 6: Typecheck**

Run:

```bash
cd frontend
npm run typecheck
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend
git commit -m "feat: 增加M4前端工程骨架"
```

---

### Task 12: Command Center Pages

**Files:**
- Create: `frontend/src/components/Layout.tsx`
- Create: `frontend/src/components/StatusBadge.tsx`
- Create: `frontend/src/components/EvidenceList.tsx`
- Create: `frontend/src/pages/OverviewPage.tsx`
- Create: `frontend/src/pages/ChatPage.tsx`
- Create: `frontend/src/pages/IncidentsPage.tsx`
- Create: `frontend/src/pages/EvidencePage.tsx`
- Create: `frontend/src/pages/ApprovalsPage.tsx`
- Create: `frontend/src/pages/GrafanaPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles/app.css`

- [ ] **Step 1: Implement layout shell**

`Layout.tsx` should render a left navigation rail, top status strip, and main content region. Navigation keys: `overview`, `chat`, `incidents`, `evidence`, `approvals`, `grafana`.

- [ ] **Step 2: Implement pages**

Implement pages with real API-backed data where endpoints exist:

- `OverviewPage`: health, recent inspections, incidents, operations, Grafana link.
- `ChatPage`: session creation, question textarea, submit button, answer panel, SSE event list.
- `IncidentsPage`: list and detail summary.
- `EvidencePage`: inspection ID input and evidence response.
- `ApprovalsPage`: create simulation request, approve, reject, list operations.
- `GrafanaPage`: external link button and iframe only when configured URL exists.

- [ ] **Step 3: Style for operational density**

Use CSS with compact panels, stable dimensions, 8px radius or less, responsive two-column Command Center, and mobile single-column layout. Avoid marketing hero layout. Ensure buttons with icons have tooltips via `title`.

- [ ] **Step 4: Typecheck**

Run:

```bash
cd frontend
npm run typecheck
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat: 增加M4控制台页面"
```

---

### Task 13: Documentation, Status, And Final Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/PROJECT_STATUS.md`

- [ ] **Step 1: Update README**

Add M4 local development commands:

```bash
datasentry db upgrade --database-path var/datasentry-m4.db
uvicorn datasentry.api.app:create_app --factory --host 127.0.0.1 --port 8000
cd frontend
npm install
npm run dev
```

Document:

- `DATASENTRY_LLM_PROVIDER=disabled|mock|openai_compatible`
- `DATASENTRY_LLM_BASE_URL`
- `DATASENTRY_LLM_MODEL`
- `DATASENTRY_LLM_API_KEY`
- The API key must stay in the environment and must not be committed.
- M4 approvals are local simulations only.

- [ ] **Step 2: Update project status**

Set current work to M4 implementation completed in local repo, list verification commands and unverified items. Keep known M3 deployment risk and MySQL anomaly risk.

- [ ] **Step 3: Run backend quality checks**

Run:

```bash
ruff format --check .
ruff check .
mypy src
pytest tests -q -W error::ResourceWarning --cov=datasentry --cov-report=term-missing --cov-fail-under=90
```

Expected: PASS.

- [ ] **Step 4: Run frontend checks**

Run:

```bash
cd frontend
npm run typecheck
npm run build
```

Expected: PASS.

- [ ] **Step 5: Manual local smoke test**

Run two terminals:

```bash
uvicorn datasentry.api.app:create_app --factory --host 127.0.0.1 --port 8000
```

```bash
cd frontend
npm run dev
```

Open `http://127.0.0.1:5173`, submit `为什么K线不更新`, and confirm:

- The page shows API and LLM status.
- The Chat page creates a session and run.
- The answer displays conclusion text or a safe failure.
- The Evidence page can load an inspection ID returned by chat when the run completes.
- The Approvals page creates and approves a `simulate_` operation.
- No API key is visible in browser text or terminal logs.

- [ ] **Step 6: Commit**

```bash
git add README.md docs/PROJECT_STATUS.md
git commit -m "docs: 更新M4使用说明"
```

---

## Final Verification Checklist

Before opening a PR or pushing a stable checkpoint, run:

```bash
git status --short --branch
ruff format --check .
ruff check .
mypy src
pytest tests -q -W error::ResourceWarning --cov=datasentry --cov-report=term-missing --cov-fail-under=90
cd frontend
npm run typecheck
npm run build
```

Expected:

- Git status contains only intentional changes before commit and is clean after commit.
- Ruff, mypy, pytest, frontend typecheck, and frontend build pass.
- Coverage remains at least 90%.
- No real `.env`, `config/targets.toml`, API key, password, private key, or production connection string is staged.

## Plan Self-Review

- Spec coverage: Tasks cover FastAPI, SSE, LLM providers, React Command Center, events, evidence, incidents, local simulated approvals, Alertmanager API, docs, and final verification.
- Scope check: Real production Runbook execution, M5 RCA memory, RBAC, SSO, Loki/Alloy, and autonomous operations remain outside M4.
- Type consistency: Chat, run, event, LLM, and operation names match the design document and planned API paths.
- Secret handling: LLM API key only enters settings and provider headers; tests verify it is not exposed by health or provider errors.
