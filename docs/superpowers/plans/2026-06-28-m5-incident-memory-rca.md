# M5 Incident Memory and RCA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build M5 incident memory so Alertmanager-triggered diagnostics create or merge Incidents, preserve timeline evidence, retrieve similar history, and generate RCA Markdown without production write operations.

**Architecture:** Add a focused `datasentry.incidents` package for fingerprints, lifecycle, search, RCA generation, and orchestration. Persist new incident memory tables in SQLite through the existing Repository pattern, expose the data through FastAPI routes, and upgrade the React Incidents page into an event workspace.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI, SQLite, pytest, Ruff, mypy, React 18, TypeScript, Vite.

---

## Cloud Instance Requirement

M5 implementation does not require the cloud instance during development. All required behavior can be built and verified with local SQLite, Alertmanager JSON fixtures, deterministic fake diagnostic runners, FastAPI `TestClient`, and frontend type/build checks.

Cloud access is optional only at the final acceptance stage for a read-only smoke check:

```bash
curl -X POST http://127.0.0.1:8000/api/alertmanager/webhook \
  -H 'Content-Type: application/json' \
  --data @tests/fixtures/alertmanager/kline_freshness_firing.json
```

Expected local result after M5: HTTP 200 with `accepted=true`, `incident_id`, and `action` equal to `created` or `updated`.

## File Structure

- Create `src/datasentry/incidents/__init__.py`: public exports for incident memory types and services.
- Create `src/datasentry/incidents/models.py`: Pydantic models for links, timeline events, fingerprints, RCA reports, action results, and detail DTOs.
- Create `src/datasentry/incidents/fingerprints.py`: deterministic fingerprint builder and stable label hashing.
- Create `src/datasentry/incidents/lifecycle.py`: pure status transition helpers.
- Create `src/datasentry/incidents/search.py`: similar incident ranking helpers.
- Create `src/datasentry/incidents/rca.py`: deterministic RCA Markdown generator.
- Create `src/datasentry/incidents/service.py`: orchestration for Alertmanager upsert, timeline writes, links, status changes, similar history, and RCA generation.
- Create `src/datasentry/storage/sql/0004_incident_memory.sql`: incident memory tables and indexes.
- Modify `src/datasentry/storage/repository.py`: add protocol methods for incident memory.
- Modify `src/datasentry/storage/sqlite.py`: implement incident memory persistence.
- Modify `src/datasentry/api/schemas.py`: add response models for webhook, incident detail, timeline, similar incidents, RCA, and export.
- Modify `src/datasentry/api/dependencies.py`: add `get_incident_service`.
- Modify `src/datasentry/api/routes/alertmanager.py`: route webhook through `IncidentService`.
- Modify `src/datasentry/api/routes/incidents.py`: add detail, timeline, similar, RCA, and export endpoints.
- Modify `frontend/src/api/types.ts`: add incident detail, timeline, similar, and RCA types.
- Modify `frontend/src/api/client.ts`: add incident detail, timeline, similar, RCA, and export calls.
- Modify `frontend/src/pages/IncidentsPage.tsx`: build incident workspace.
- Modify `README.md`: document M5 local usage and cloud smoke boundary.
- Modify `docs/PROJECT_STATUS.md`: update M5 implementation progress and verification results.

---

### Task 1: Incident Memory Domain Models

**Files:**
- Create: `src/datasentry/incidents/__init__.py`
- Create: `src/datasentry/incidents/models.py`
- Test: `tests/unit/incidents/test_models.py`

- [ ] **Step 1: Write failing model tests**

Add `tests/unit/incidents/test_models.py`:

```python
from datetime import UTC, datetime

import pytest

from datasentry.domain import IncidentStatus, Severity
from datasentry.incidents import (
    IncidentFingerprint,
    IncidentLink,
    IncidentLinkKind,
    IncidentRCAReport,
    IncidentTimelineEvent,
    IncidentTimelineEventType,
)

NOW = datetime(2026, 6, 28, 9, 0, tzinfo=UTC)


def test_timeline_event_requires_non_empty_summary() -> None:
    with pytest.raises(ValueError, match="String should have at least 1 character"):
        IncidentTimelineEvent(
            incident_id="incident-1",
            event_type=IncidentTimelineEventType.ALERT_FIRED,
            summary="",
            source="alertmanager",
            payload={},
            occurred_at=NOW,
        )


def test_link_keeps_external_identifier_and_kind() -> None:
    link = IncidentLink(
        incident_id="incident-1",
        kind=IncidentLinkKind.FINDING,
        target_id="finding-1",
        summary="关联 confirmed Finding",
        created_at=NOW,
    )

    assert link.kind is IncidentLinkKind.FINDING
    assert link.target_id == "finding-1"


def test_fingerprint_tracks_active_window() -> None:
    fingerprint = IncidentFingerprint(
        incident_id="incident-1",
        component="flink",
        failure_type="kline_freshness",
        stable_labels_hash="abc123",
        severity=Severity.WARNING,
        first_seen_at=NOW,
        last_seen_at=NOW,
    )

    assert fingerprint.component == "flink"
    assert fingerprint.last_seen_at == NOW


def test_rca_report_requires_markdown_and_status_snapshot() -> None:
    report = IncidentRCAReport(
        incident_id="incident-1",
        version=1,
        markdown="# RCA\n\n历史事件仅用于经验参考；当前状态必须以本次只读巡检证据为准。",
        structured={
            "status": IncidentStatus.INVESTIGATING.value,
            "severity": Severity.WARNING.value,
        },
        generated_by="deterministic_template",
        created_at=NOW,
    )

    assert report.version == 1
    assert "历史事件仅用于经验参考" in report.markdown
```

- [ ] **Step 2: Run model tests to verify failure**

Run:

```bash
.venv/bin/pytest tests/unit/incidents/test_models.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'datasentry.incidents'`.

- [ ] **Step 3: Implement models and exports**

Create `src/datasentry/incidents/models.py`:

```python
"""Incident 记忆领域模型。"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field, field_validator, model_validator

from datasentry.domain import Incident, IncidentStatus, Severity
from datasentry.domain.common import (
    DomainModel,
    new_id,
    require_aware_datetime,
    utc_now,
)


class IncidentLinkKind(StrEnum):
    INSPECTION = "inspection"
    FINDING = "finding"
    OPERATION = "operation"
    ALERT = "alert"
    CHAT_RUN = "chat_run"
    RCA_REPORT = "rca_report"


class IncidentTimelineEventType(StrEnum):
    ALERT_FIRED = "alert_fired"
    ALERT_RESOLVED = "alert_resolved"
    DIAGNOSIS_STARTED = "diagnosis_started"
    DIAGNOSIS_COMPLETED = "diagnosis_completed"
    DIAGNOSIS_FAILED = "diagnosis_failed"
    FINDING_ADDED = "finding_added"
    OPERATION_LINKED = "operation_linked"
    STATUS_CHANGED = "status_changed"
    VERIFICATION_COMPLETED = "verification_completed"
    RCA_GENERATED = "rca_generated"
    MANUAL_NOTE_ADDED = "manual_note_added"


class IncidentAction(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    RESOLVED_SIGNAL_RECORDED = "resolved_signal_recorded"
    DIAGNOSIS_FAILED = "diagnosis_failed"
    IGNORED = "ignored"


class IncidentLink(DomainModel):
    id: str = Field(default_factory=new_id)
    incident_id: str = Field(min_length=1)
    kind: IncidentLinkKind
    target_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=utc_now)

    _normalize_created_at = field_validator("created_at")(require_aware_datetime)


class IncidentTimelineEvent(DomainModel):
    id: str = Field(default_factory=new_id)
    incident_id: str = Field(min_length=1)
    event_type: IncidentTimelineEventType
    summary: str = Field(min_length=1)
    source: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=utc_now)

    _normalize_occurred_at = field_validator("occurred_at")(require_aware_datetime)


class IncidentFingerprint(DomainModel):
    id: str = Field(default_factory=new_id)
    incident_id: str = Field(min_length=1)
    component: str = Field(min_length=1)
    failure_type: str = Field(min_length=1)
    stable_labels_hash: str = Field(min_length=1)
    severity: Severity
    first_seen_at: datetime = Field(default_factory=utc_now)
    last_seen_at: datetime = Field(default_factory=utc_now)

    _normalize_first_seen_at = field_validator("first_seen_at")(require_aware_datetime)
    _normalize_last_seen_at = field_validator("last_seen_at")(require_aware_datetime)

    @model_validator(mode="after")
    def validate_window(self) -> "IncidentFingerprint":
        if self.last_seen_at < self.first_seen_at:
            raise ValueError("last_seen_at 不能早于 first_seen_at")
        return self


class IncidentRCAReport(DomainModel):
    id: str = Field(default_factory=new_id)
    incident_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    markdown: str = Field(min_length=1)
    structured: dict[str, Any] = Field(default_factory=dict)
    generated_by: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=utc_now)

    _normalize_created_at = field_validator("created_at")(require_aware_datetime)


class IncidentDetail(DomainModel):
    incident: Incident
    links: list[IncidentLink]
    timeline: list[IncidentTimelineEvent]
    fingerprints: list[IncidentFingerprint]
    latest_rca: IncidentRCAReport | None = None


class IncidentUpsertResult(DomainModel):
    accepted: bool = True
    incident_id: str
    action: IncidentAction
    status: IncidentStatus
    deduplication_key: str
    diagnosis_question: str
```

Create `src/datasentry/incidents/__init__.py`:

```python
"""Incident 记忆、生命周期和 RCA 能力。"""

from datasentry.incidents.models import (
    IncidentAction,
    IncidentDetail,
    IncidentFingerprint,
    IncidentLink,
    IncidentLinkKind,
    IncidentRCAReport,
    IncidentTimelineEvent,
    IncidentTimelineEventType,
    IncidentUpsertResult,
)

__all__ = [
    "IncidentAction",
    "IncidentDetail",
    "IncidentFingerprint",
    "IncidentLink",
    "IncidentLinkKind",
    "IncidentRCAReport",
    "IncidentTimelineEvent",
    "IncidentTimelineEventType",
    "IncidentUpsertResult",
]
```

- [ ] **Step 4: Run model tests to verify pass**

Run:

```bash
.venv/bin/pytest tests/unit/incidents/test_models.py -q
```

Expected: `4 passed`.

- [ ] **Step 5: Commit domain models**

```bash
git add src/datasentry/incidents/__init__.py src/datasentry/incidents/models.py tests/unit/incidents/test_models.py
git commit -m "feat: 增加M5事件记忆模型"
```

---

### Task 2: SQLite Incident Memory Persistence

**Files:**
- Create: `src/datasentry/storage/sql/0004_incident_memory.sql`
- Modify: `src/datasentry/storage/repository.py`
- Modify: `src/datasentry/storage/sqlite.py`
- Test: `tests/integration/storage/test_migrations.py`
- Test: `tests/integration/storage/test_sqlite_repository.py`

- [ ] **Step 1: Write failing migration and repository tests**

Append to `tests/integration/storage/test_migrations.py`:

```python
def test_migration_0004_creates_incident_memory_tables(tmp_path) -> None:
    from datasentry.storage.migrations import connect, upgrade_database

    database_path = tmp_path / "datasentry.db"
    version = upgrade_database(database_path)

    with connect(database_path) as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert version >= 4
    assert "incident_links" in tables
    assert "incident_timeline_events" in tables
    assert "incident_fingerprints" in tables
    assert "incident_rca_reports" in tables
```

Append to `tests/integration/storage/test_sqlite_repository.py`:

```python
def test_incident_memory_round_trip(tmp_path) -> None:
    from datasentry.domain import Incident, Severity
    from datasentry.incidents import (
        IncidentFingerprint,
        IncidentLink,
        IncidentLinkKind,
        IncidentRCAReport,
        IncidentTimelineEvent,
        IncidentTimelineEventType,
    )
    from datasentry.storage import SQLiteRepository

    database_path = tmp_path / "datasentry.db"
    incident = Incident(
        id="incident-memory-1",
        title="K线数据不更新",
        symptom="页面显示旧 Kline",
        severity=Severity.WARNING,
    )
    link = IncidentLink(
        incident_id=incident.id,
        kind=IncidentLinkKind.ALERT,
        target_id="dedup-key-1",
        summary="Alertmanager firing",
    )
    event = IncidentTimelineEvent(
        incident_id=incident.id,
        event_type=IncidentTimelineEventType.ALERT_FIRED,
        summary="收到 KlineFreshnessStale 告警",
        source="alertmanager",
        payload={"token": "secret-token", "status": "firing"},
    )
    fingerprint = IncidentFingerprint(
        incident_id=incident.id,
        component="flink",
        failure_type="KlineFreshnessStale",
        stable_labels_hash="hash-1",
        severity=Severity.WARNING,
    )
    report = IncidentRCAReport(
        incident_id=incident.id,
        version=1,
        markdown="# RCA\n\n历史事件仅用于经验参考；当前状态必须以本次只读巡检证据为准。",
        structured={"unknowns": []},
        generated_by="deterministic_template",
    )

    with SQLiteRepository(database_path) as repository:
        repository.save_incident(incident)
        repository.save_incident_link(link)
        repository.save_timeline_event(event)
        repository.save_incident_fingerprint(fingerprint)
        repository.save_rca_report(report)

        assert repository.list_incident_links(incident.id)[0].target_id == "dedup-key-1"
        assert repository.list_timeline_events(incident.id)[0].payload["token"] == "[REDACTED]"
        assert repository.find_active_incident_by_fingerprint(fingerprint) == incident.id
        assert repository.get_latest_rca_report(incident.id).version == 1
```

- [ ] **Step 2: Run storage tests to verify failure**

Run:

```bash
.venv/bin/pytest tests/integration/storage/test_migrations.py::test_migration_0004_creates_incident_memory_tables tests/integration/storage/test_sqlite_repository.py::test_incident_memory_round_trip -q
```

Expected: fail because migration and Repository methods do not exist.

- [ ] **Step 3: Add SQLite migration**

Create `src/datasentry/storage/sql/0004_incident_memory.sql`:

```sql
CREATE TABLE incident_links (
    id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (
        kind IN ('inspection', 'finding', 'operation', 'alert', 'chat_run', 'rca_report')
    ),
    target_id TEXT NOT NULL CHECK (length(trim(target_id)) > 0),
    summary TEXT NOT NULL CHECK (length(trim(summary)) > 0),
    created_at TEXT NOT NULL,
    FOREIGN KEY (incident_id) REFERENCES incidents(id) ON DELETE CASCADE,
    UNIQUE (incident_id, kind, target_id)
);

CREATE TABLE incident_timeline_events (
    id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (
        event_type IN (
            'alert_fired',
            'alert_resolved',
            'diagnosis_started',
            'diagnosis_completed',
            'diagnosis_failed',
            'finding_added',
            'operation_linked',
            'status_changed',
            'verification_completed',
            'rca_generated',
            'manual_note_added'
        )
    ),
    summary TEXT NOT NULL CHECK (length(trim(summary)) > 0),
    source TEXT NOT NULL CHECK (length(trim(source)) > 0),
    payload_json TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    FOREIGN KEY (incident_id) REFERENCES incidents(id) ON DELETE CASCADE
);

CREATE TABLE incident_fingerprints (
    id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    component TEXT NOT NULL CHECK (length(trim(component)) > 0),
    failure_type TEXT NOT NULL CHECK (length(trim(failure_type)) > 0),
    stable_labels_hash TEXT NOT NULL CHECK (length(trim(stable_labels_hash)) > 0),
    severity TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    FOREIGN KEY (incident_id) REFERENCES incidents(id) ON DELETE CASCADE,
    UNIQUE (incident_id, component, failure_type, stable_labels_hash)
);

CREATE TABLE incident_rca_reports (
    id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    markdown TEXT NOT NULL CHECK (length(trim(markdown)) > 0),
    structured_json TEXT NOT NULL,
    generated_by TEXT NOT NULL CHECK (length(trim(generated_by)) > 0),
    created_at TEXT NOT NULL,
    FOREIGN KEY (incident_id) REFERENCES incidents(id) ON DELETE CASCADE,
    UNIQUE (incident_id, version)
);

CREATE INDEX idx_incident_links_incident_kind
    ON incident_links(incident_id, kind);
CREATE INDEX idx_incident_timeline_incident_time
    ON incident_timeline_events(incident_id, occurred_at);
CREATE INDEX idx_incident_fingerprints_lookup
    ON incident_fingerprints(component, failure_type, stable_labels_hash, last_seen_at);
CREATE INDEX idx_incident_rca_incident_version
    ON incident_rca_reports(incident_id, version);
```

- [ ] **Step 4: Extend Repository protocol and SQLite implementation**

Add imports in `src/datasentry/storage/repository.py`:

```python
from datasentry.incidents import (
    IncidentFingerprint,
    IncidentLink,
    IncidentRCAReport,
    IncidentTimelineEvent,
)
```

Add protocol methods:

```python
    def save_incident_link(self, link: IncidentLink) -> None:
        raise NotImplementedError  # pragma: no cover

    def list_incident_links(self, incident_id: str) -> list[IncidentLink]:
        raise NotImplementedError  # pragma: no cover

    def save_timeline_event(self, event: IncidentTimelineEvent) -> None:
        raise NotImplementedError  # pragma: no cover

    def list_timeline_events(self, incident_id: str) -> list[IncidentTimelineEvent]:
        raise NotImplementedError  # pragma: no cover

    def save_incident_fingerprint(self, fingerprint: IncidentFingerprint) -> None:
        raise NotImplementedError  # pragma: no cover

    def find_active_incident_by_fingerprint(
        self,
        fingerprint: IncidentFingerprint,
    ) -> str | None:
        raise NotImplementedError  # pragma: no cover

    def search_similar_incidents(
        self,
        fingerprint: IncidentFingerprint,
        *,
        limit: int = 5,
    ) -> list[Incident]:
        raise NotImplementedError  # pragma: no cover

    def save_rca_report(self, report: IncidentRCAReport) -> None:
        raise NotImplementedError  # pragma: no cover

    def get_latest_rca_report(self, incident_id: str) -> IncidentRCAReport | None:
        raise NotImplementedError  # pragma: no cover

    def list_rca_reports(self, incident_id: str) -> list[IncidentRCAReport]:
        raise NotImplementedError  # pragma: no cover
```

In `src/datasentry/storage/sqlite.py`, implement the methods using existing `_dump_datetime`, `_load_datetime`, JSON helpers, `_validate_list_limit`, and `redact_text`. Use `INSERT OR IGNORE` for links and `INSERT ... ON CONFLICT ... DO UPDATE` for fingerprints so repeated alerts are idempotent.

- [ ] **Step 5: Run storage tests to verify pass**

Run:

```bash
.venv/bin/pytest tests/integration/storage/test_migrations.py tests/integration/storage/test_sqlite_repository.py -q
```

Expected: storage integration tests pass.

- [ ] **Step 6: Commit persistence**

```bash
git add src/datasentry/storage/sql/0004_incident_memory.sql src/datasentry/storage/repository.py src/datasentry/storage/sqlite.py tests/integration/storage/test_migrations.py tests/integration/storage/test_sqlite_repository.py
git commit -m "feat: 持久化M5事件记忆"
```

---

### Task 3: Fingerprints, Lifecycle, and Similar Search

**Files:**
- Create: `src/datasentry/incidents/fingerprints.py`
- Create: `src/datasentry/incidents/lifecycle.py`
- Create: `src/datasentry/incidents/search.py`
- Modify: `src/datasentry/incidents/__init__.py`
- Test: `tests/unit/incidents/test_fingerprints.py`
- Test: `tests/unit/incidents/test_lifecycle.py`
- Test: `tests/unit/incidents/test_search.py`

- [ ] **Step 1: Write failing behavior tests**

Add `tests/unit/incidents/test_fingerprints.py`:

```python
from datasentry.domain import Severity
from datasentry.incidents import build_alert_fingerprint, stable_labels_hash


def test_stable_labels_hash_ignores_unstable_annotations() -> None:
    labels = {
        "alertname": "KlineFreshnessStale",
        "component": "flink",
        "instance": "data1:8081",
        "description": "changes often",
    }

    assert stable_labels_hash(labels) == stable_labels_hash(dict(reversed(labels.items())))


def test_build_alert_fingerprint_uses_component_and_alertname() -> None:
    fingerprint = build_alert_fingerprint(
        incident_id="incident-1",
        labels={
            "alertname": "KlineFreshnessStale",
            "component": "flink",
            "severity": "warning",
        },
    )

    assert fingerprint.component == "flink"
    assert fingerprint.failure_type == "KlineFreshnessStale"
    assert fingerprint.severity is Severity.WARNING
```

Add `tests/unit/incidents/test_lifecycle.py`:

```python
from datasentry.domain import IncidentStatus
from datasentry.incidents import next_status_for_alert, next_status_for_diagnosis_failure


def test_new_firing_alert_moves_to_investigating() -> None:
    assert next_status_for_alert(None, alert_status="firing") is IncidentStatus.INVESTIGATING


def test_resolved_alert_moves_active_incident_to_verifying() -> None:
    assert (
        next_status_for_alert(IncidentStatus.INVESTIGATING, alert_status="resolved")
        is IncidentStatus.VERIFYING
    )


def test_diagnosis_failure_blocks_unresolved_incident() -> None:
    assert (
        next_status_for_diagnosis_failure(IncidentStatus.INVESTIGATING)
        is IncidentStatus.BLOCKED
    )
```

Add `tests/unit/incidents/test_search.py`:

```python
from datetime import UTC, datetime

from datasentry.domain import Incident, Severity
from datasentry.incidents import IncidentSearchCandidate, rank_similar_incidents

NOW = datetime(2026, 6, 28, 10, 0, tzinfo=UTC)


def test_rank_similar_incidents_prefers_exact_component_and_failure_type() -> None:
    exact = IncidentSearchCandidate(
        incident=Incident(
            id="incident-1",
            title="K线延迟",
            symptom="K线不更新",
            severity=Severity.WARNING,
            opened_at=NOW,
            updated_at=NOW,
        ),
        component="flink",
        failure_type="KlineFreshnessStale",
        stable_labels_hash="hash-1",
        root_cause="Flink Job lag",
    )
    component_only = exact.model_copy(
        update={
            "incident": exact.incident.model_copy(update={"id": "incident-2"}),
            "failure_type": "KafkaConsumerLagHigh",
        }
    )

    ranked = rank_similar_incidents(
        [component_only, exact],
        component="flink",
        failure_type="KlineFreshnessStale",
        stable_labels_hash="hash-1",
        root_cause_keywords=["Flink"],
    )

    assert [candidate.incident.id for candidate in ranked] == ["incident-1", "incident-2"]
```

- [ ] **Step 2: Run unit tests to verify failure**

Run:

```bash
.venv/bin/pytest tests/unit/incidents/test_fingerprints.py tests/unit/incidents/test_lifecycle.py tests/unit/incidents/test_search.py -q
```

Expected: fail because helper modules and exports do not exist.

- [ ] **Step 3: Implement helpers**

Create `src/datasentry/incidents/fingerprints.py` with:

```python
"""Incident fingerprint 构建。"""

from datetime import datetime
from hashlib import sha256

from datasentry.domain import Severity
from datasentry.domain.common import utc_now
from datasentry.incidents.models import IncidentFingerprint

STABLE_LABELS = ("alertname", "component", "service", "job", "instance")


def stable_labels_hash(labels: dict[str, str]) -> str:
    parts = [f"{name}={labels.get(name, 'unknown')}" for name in STABLE_LABELS]
    return sha256("|".join(parts).encode("utf-8")).hexdigest()


def _severity(value: str | None) -> Severity:
    if value == Severity.CRITICAL.value:
        return Severity.CRITICAL
    if value == Severity.INFO.value:
        return Severity.INFO
    return Severity.WARNING


def build_alert_fingerprint(
    *,
    incident_id: str,
    labels: dict[str, str],
    observed_at: datetime | None = None,
) -> IncidentFingerprint:
    now = observed_at or utc_now()
    return IncidentFingerprint(
        incident_id=incident_id,
        component=labels.get("component") or labels.get("job") or "streamlake",
        failure_type=labels.get("alertname") or "streamlake_status",
        stable_labels_hash=stable_labels_hash(labels),
        severity=_severity(labels.get("severity")),
        first_seen_at=now,
        last_seen_at=now,
    )
```

Create `src/datasentry/incidents/lifecycle.py` with:

```python
"""Incident 生命周期纯函数。"""

from datasentry.domain import IncidentStatus


def next_status_for_alert(
    current: IncidentStatus | None,
    *,
    alert_status: str,
) -> IncidentStatus:
    if alert_status == "resolved":
        if current is IncidentStatus.RESOLVED:
            return IncidentStatus.RESOLVED
        return IncidentStatus.VERIFYING
    if current in {IncidentStatus.BLOCKED, IncidentStatus.ESCALATED}:
        return current
    return IncidentStatus.INVESTIGATING


def next_status_for_diagnosis_failure(current: IncidentStatus) -> IncidentStatus:
    if current is IncidentStatus.RESOLVED:
        return IncidentStatus.RESOLVED
    return IncidentStatus.BLOCKED
```

Create `src/datasentry/incidents/search.py` with `IncidentSearchCandidate` and `rank_similar_incidents` scoring exact fingerprint as 100, component as 30, failure type as 30, root cause keyword as 20, severity match as 10.

Export helpers from `src/datasentry/incidents/__init__.py`.

- [ ] **Step 4: Run helper tests to verify pass**

Run:

```bash
.venv/bin/pytest tests/unit/incidents/test_fingerprints.py tests/unit/incidents/test_lifecycle.py tests/unit/incidents/test_search.py -q
```

Expected: helper tests pass.

- [ ] **Step 5: Commit helper logic**

```bash
git add src/datasentry/incidents/fingerprints.py src/datasentry/incidents/lifecycle.py src/datasentry/incidents/search.py src/datasentry/incidents/__init__.py tests/unit/incidents/test_fingerprints.py tests/unit/incidents/test_lifecycle.py tests/unit/incidents/test_search.py
git commit -m "feat: 增加事件指纹和生命周期规则"
```

---

### Task 4: Deterministic RCA Generator

**Files:**
- Create: `src/datasentry/incidents/rca.py`
- Modify: `src/datasentry/incidents/__init__.py`
- Test: `tests/unit/incidents/test_rca.py`

- [ ] **Step 1: Write failing RCA tests**

Add `tests/unit/incidents/test_rca.py`:

```python
from datetime import UTC, datetime

from datasentry.domain import Incident, Severity
from datasentry.incidents import (
    IncidentTimelineEvent,
    IncidentTimelineEventType,
    build_rca_report,
)

NOW = datetime(2026, 6, 28, 11, 0, tzinfo=UTC)


def test_build_rca_report_contains_boundary_statement_and_timeline() -> None:
    incident = Incident(
        id="incident-1",
        title="K线数据不更新",
        symptom="页面显示旧 Kline",
        severity=Severity.WARNING,
        root_cause="Flink Kline Job 延迟",
        opened_at=NOW,
        updated_at=NOW,
    )
    timeline = [
        IncidentTimelineEvent(
            incident_id=incident.id,
            event_type=IncidentTimelineEventType.ALERT_FIRED,
            summary="收到 KlineFreshnessStale 告警",
            source="alertmanager",
            occurred_at=NOW,
        )
    ]

    report = build_rca_report(
        incident=incident,
        timeline=timeline,
        evidence_summaries=["Doris kline_1min 业务时间滞后"],
        similar_summaries=["2026-06-20 曾出现 Flink lag"],
        unknowns=["需要人工确认 API 缓存"],
        next_version=1,
    )

    assert report.version == 1
    assert "历史事件仅用于经验参考；当前状态必须以本次只读巡检证据为准。" in report.markdown
    assert "收到 KlineFreshnessStale 告警" in report.markdown
    assert report.structured["unknowns"] == ["需要人工确认 API 缓存"]
```

- [ ] **Step 2: Run RCA tests to verify failure**

Run:

```bash
.venv/bin/pytest tests/unit/incidents/test_rca.py -q
```

Expected: fail because `build_rca_report` does not exist.

- [ ] **Step 3: Implement deterministic RCA builder**

Create `src/datasentry/incidents/rca.py`:

```python
"""确定性 RCA Markdown 生成。"""

from datasentry.domain import Incident
from datasentry.incidents.models import IncidentRCAReport, IncidentTimelineEvent
from datasentry.tools.redaction import redact_text

BOUNDARY = "历史事件仅用于经验参考；当前状态必须以本次只读巡检证据为准。"


def build_rca_report(
    *,
    incident: Incident,
    timeline: list[IncidentTimelineEvent],
    evidence_summaries: list[str],
    similar_summaries: list[str],
    unknowns: list[str],
    next_version: int,
) -> IncidentRCAReport:
    timeline_lines = [
        f"- {event.occurred_at.isoformat()} [{event.event_type.value}] {redact_text(event.summary)}"
        for event in timeline
    ]
    evidence_lines = [f"- {redact_text(summary)}" for summary in evidence_summaries]
    similar_lines = [f"- {redact_text(summary)}" for summary in similar_summaries]
    unknown_lines = [f"- {redact_text(unknown)}" for unknown in unknowns]
    markdown = "\n".join(
        [
            f"# RCA：{redact_text(incident.title)}",
            "",
            f"> {BOUNDARY}",
            "",
            "## 事件摘要",
            "",
            f"- 状态：{incident.status.value}",
            f"- 严重级别：{incident.severity.value}",
            f"- 症状：{redact_text(incident.symptom)}",
            f"- 根因草稿：{redact_text(incident.root_cause or '未知')}",
            "",
            "## 时间线",
            "",
            *(timeline_lines or ["- 暂无时间线事件"]),
            "",
            "## 证据",
            "",
            *(evidence_lines or ["- 暂无证据摘要"]),
            "",
            "## 历史相似事件",
            "",
            *(similar_lines or ["- 暂无相似历史事件"]),
            "",
            "## 未知项",
            "",
            *(unknown_lines or ["- 暂无未知项"]),
            "",
        ]
    )
    return IncidentRCAReport(
        incident_id=incident.id,
        version=next_version,
        markdown=markdown,
        structured={
            "status": incident.status.value,
            "severity": incident.severity.value,
            "unknowns": [redact_text(unknown) for unknown in unknowns],
            "boundary": BOUNDARY,
        },
        generated_by="deterministic_template",
    )
```

Export `build_rca_report` from `src/datasentry/incidents/__init__.py`.

- [ ] **Step 4: Run RCA tests to verify pass**

Run:

```bash
.venv/bin/pytest tests/unit/incidents/test_rca.py -q
```

Expected: RCA tests pass.

- [ ] **Step 5: Commit RCA generator**

```bash
git add src/datasentry/incidents/rca.py src/datasentry/incidents/__init__.py tests/unit/incidents/test_rca.py
git commit -m "feat: 生成事件RCA草稿"
```

---

### Task 5: IncidentService Alertmanager Upsert

**Files:**
- Create: `src/datasentry/incidents/service.py`
- Modify: `src/datasentry/incidents/__init__.py`
- Test: `tests/unit/incidents/test_service.py`

- [ ] **Step 1: Write failing service tests with fake runner**

Add `tests/unit/incidents/test_service.py`:

```python
import json
from pathlib import Path

from datasentry.incidents import IncidentAction, IncidentService
from datasentry.notifications import parse_alertmanager_payload
from datasentry.storage import SQLiteRepository


class FakeDiagnosisRunner:
    def run(self, question: str):
        from datetime import UTC, datetime

        from datasentry.diagnosis import DiagnosisResult, PreparedDiagnosis
        from datasentry.domain import (
            Evidence,
            EvidenceStatus,
            Finding,
            Inspection,
            InspectionStatus,
            Severity,
        )
        from datasentry.tools import LiveInspectionResult

        now = datetime(2026, 6, 28, 12, 0, tzinfo=UTC)
        inspection = Inspection(
            question=question,
            scope=["streamlake"],
            status=InspectionStatus.COMPLETED,
            summary="Kline freshness stale",
            started_at=now,
            finished_at=now,
        )
        finding = Finding(
            inspection_id=inspection.id,
            severity=Severity.WARNING,
            status=EvidenceStatus.CONFIRMED,
            claim="Kline 数据未持续推进",
            evidence=[
                Evidence(
                    claim="Doris 新鲜度滞后",
                    status=EvidenceStatus.CONFIRMED,
                    source="doris",
                    target="kline_1min",
                    observed_at=now,
                    summary="业务时间滞后",
                )
            ],
            impact="页面可能展示旧 Kline",
            recommendation="检查 Flink Kline Job",
            created_at=now,
        )
        prepared = PreparedDiagnosis(inspection=inspection, topic_ids=("streamlake-kline",))
        diagnosis = DiagnosisResult(prepared=prepared, aggregate=type("Aggregate", (), {"findings": [finding]})())
        return LiveInspectionResult(diagnosis=diagnosis, tool_invocations=[])


def test_service_creates_incident_from_alertmanager_payload(tmp_path) -> None:
    payload = parse_alertmanager_payload(
        json.loads(Path("tests/fixtures/alertmanager/kline_freshness_firing.json").read_text())
    )
    with SQLiteRepository(tmp_path / "datasentry.db") as repository:
        service = IncidentService(repository=repository, diagnosis_runner=FakeDiagnosisRunner())

        result = service.handle_alertmanager_payload(payload)

        assert result.action is IncidentAction.CREATED
        detail = service.get_detail(result.incident_id)
        assert detail.incident.title.startswith("KlineFreshnessStale")
        assert len(detail.timeline) >= 2
        assert detail.links


def test_service_merges_repeated_alert_into_same_incident(tmp_path) -> None:
    payload = parse_alertmanager_payload(
        json.loads(Path("tests/fixtures/alertmanager/kline_freshness_firing.json").read_text())
    )
    with SQLiteRepository(tmp_path / "datasentry.db") as repository:
        service = IncidentService(repository=repository, diagnosis_runner=FakeDiagnosisRunner())

        first = service.handle_alertmanager_payload(payload)
        second = service.handle_alertmanager_payload(payload)

        assert second.incident_id == first.incident_id
        assert second.action is IncidentAction.UPDATED
```

- [ ] **Step 2: Run service tests to verify failure**

Run:

```bash
.venv/bin/pytest tests/unit/incidents/test_service.py -q
```

Expected: fail because `IncidentService` does not exist.

- [ ] **Step 3: Implement IncidentService**

Create `src/datasentry/incidents/service.py` with:

- `DiagnosisRunner` protocol matching `run(question: str) -> LiveInspectionResult`.
- `IncidentService.handle_alertmanager_payload(payload) -> IncidentUpsertResult`.
- `get_detail(incident_id) -> IncidentDetail`.
- `find_similar(incident_id, limit=5) -> list[Incident]`.
- `generate_rca(incident_id) -> IncidentRCAReport`.

Implementation details:

- Use `build_alert_deduplication_key(payload)` and `map_alert_to_question(payload)`.
- Build labels from `payload.common_labels | payload.group_labels | payload.primary_alert.labels`.
- Create a temporary fingerprint with `incident_id="pending"` to search active incidents; after creating a new Incident, persist the same fingerprint with the actual incident ID.
- Save `alert_fired` or `alert_resolved` timeline event first.
- Run diagnosis for firing alerts; on success link inspection and findings, append `diagnosis_completed` and `finding_added`.
- On diagnosis exception, append `diagnosis_failed`, set status using `next_status_for_diagnosis_failure`, and return `IncidentAction.DIAGNOSIS_FAILED`.
- For repeated firing alerts with the same active fingerprint, update the existing Incident and return `IncidentAction.UPDATED`.
- For resolved alerts, set status to `verifying`, append `alert_resolved`, and return `IncidentAction.RESOLVED_SIGNAL_RECORDED`.

- [ ] **Step 4: Run service tests to verify pass**

Run:

```bash
.venv/bin/pytest tests/unit/incidents/test_service.py -q
```

Expected: service tests pass.

- [ ] **Step 5: Commit service**

```bash
git add src/datasentry/incidents/service.py src/datasentry/incidents/__init__.py tests/unit/incidents/test_service.py
git commit -m "feat: 接入告警驱动Incident服务"
```

---

### Task 6: FastAPI Incident Memory Endpoints

**Files:**
- Modify: `src/datasentry/api/dependencies.py`
- Modify: `src/datasentry/api/schemas.py`
- Modify: `src/datasentry/api/routes/alertmanager.py`
- Modify: `src/datasentry/api/routes/incidents.py`
- Test: `tests/integration/api/test_alertmanager_api.py`
- Test: `tests/integration/api/test_incidents_evidence_operations.py`

- [ ] **Step 1: Write failing API tests**

Update `tests/integration/api/test_alertmanager_api.py` so `test_alertmanager_webhook_parses_payload` asserts:

```python
    assert body["accepted"] is True
    assert body["incident_id"]
    assert body["action"] in {"created", "updated"}
    assert body["status"] in {"investigating", "blocked"}
    assert body["diagnosis_question"] == "为什么 K线数据不更新"
```

Add to `tests/integration/api/test_incidents_evidence_operations.py`:

```python
def test_incident_detail_timeline_rca_and_export_routes(tmp_path, monkeypatch) -> None:
    import json
    from pathlib import Path

    monkeypatch.setenv("DATASENTRY_DATABASE_PATH", str(tmp_path / "datasentry.db"))
    client = TestClient(create_app(Settings()))
    payload = json.loads(
        Path("tests/fixtures/alertmanager/kline_freshness_firing.json").read_text(
            encoding="utf-8",
        )
    )

    created = client.post("/api/alertmanager/webhook", json=payload)
    incident_id = created.json()["incident_id"]

    detail = client.get(f"/api/incidents/{incident_id}")
    timeline = client.get(f"/api/incidents/{incident_id}/timeline")
    rca = client.post(f"/api/incidents/{incident_id}/rca")
    exported = client.get(f"/api/incidents/{incident_id}/export")

    assert detail.status_code == 200
    assert detail.json()["incident"]["id"] == incident_id
    assert timeline.status_code == 200
    assert rca.status_code == 200
    assert "历史事件仅用于经验参考" in rca.json()["markdown"]
    assert exported.status_code == 200
    assert "text/markdown" in exported.headers["content-type"]
```

- [ ] **Step 2: Run API tests to verify failure**

Run:

```bash
.venv/bin/pytest tests/integration/api/test_alertmanager_api.py tests/integration/api/test_incidents_evidence_operations.py -q
```

Expected: fail because routes still return M4 payloads and no RCA/export endpoints exist.

- [ ] **Step 3: Add dependency and route implementations**

In `src/datasentry/api/dependencies.py`, add:

```python
from datasentry.incidents import IncidentService


def get_incident_service(
    settings: Annotated[Settings, Depends(get_settings)],
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> IncidentService:
    targets = TargetCatalog.load(settings.targets_file)
    live_inspection = build_live_inspection_service(
        repository=repository,
        targets=targets,
        knowledge_root=Path("knowledge"),
    )
    return IncidentService(repository=repository, diagnosis_runner=live_inspection)
```

In `src/datasentry/api/routes/alertmanager.py`, inject `IncidentService` and return `jsonable_encoder(result)`.

In `src/datasentry/api/routes/incidents.py`, add:

- `GET /incidents/{incident_id}/timeline`
- `GET /incidents/{incident_id}/similar`
- `POST /incidents/{incident_id}/rca`
- `GET /incidents/{incident_id}/export` returning `PlainTextResponse(media_type="text/markdown; charset=utf-8")`

- [ ] **Step 4: Run API tests to verify pass**

Run:

```bash
.venv/bin/pytest tests/integration/api/test_alertmanager_api.py tests/integration/api/test_incidents_evidence_operations.py -q
```

Expected: API integration tests pass.

- [ ] **Step 5: Commit API endpoints**

```bash
git add src/datasentry/api/dependencies.py src/datasentry/api/schemas.py src/datasentry/api/routes/alertmanager.py src/datasentry/api/routes/incidents.py tests/integration/api/test_alertmanager_api.py tests/integration/api/test_incidents_evidence_operations.py
git commit -m "feat: 暴露M5事件记忆API"
```

---

### Task 7: React Incident Workspace

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/IncidentsPage.tsx`

- [ ] **Step 1: Update frontend types and client**

In `frontend/src/api/types.ts`, add:

```ts
export type IncidentLink = {
  id: string;
  incident_id: string;
  kind: string;
  target_id: string;
  summary: string;
  created_at: string;
};

export type IncidentTimelineEvent = {
  id: string;
  incident_id: string;
  event_type: string;
  summary: string;
  source: string;
  payload: Record<string, unknown>;
  occurred_at: string;
};

export type IncidentFingerprint = {
  id: string;
  incident_id: string;
  component: string;
  failure_type: string;
  stable_labels_hash: string;
  severity: string;
  first_seen_at: string;
  last_seen_at: string;
};

export type IncidentRCAReport = {
  id: string;
  incident_id: string;
  version: number;
  markdown: string;
  structured: Record<string, unknown>;
  generated_by: string;
  created_at: string;
};

export type IncidentDetail = {
  incident: Incident;
  links: IncidentLink[];
  timeline: IncidentTimelineEvent[];
  fingerprints: IncidentFingerprint[];
  latest_rca: IncidentRCAReport | null;
};
```

In `frontend/src/api/client.ts`, add:

```ts
  incident: (incidentId: string) =>
    requestJson<IncidentDetail>(`/api/incidents/${incidentId}`),
  incidentSimilar: (incidentId: string) =>
    requestJson<Incident[]>(`/api/incidents/${incidentId}/similar`),
  generateIncidentRca: (incidentId: string) =>
    requestJson<IncidentRCAReport>(`/api/incidents/${incidentId}/rca`, { method: "POST" }),
  exportIncident: (incidentId: string) =>
    requestText(`/api/incidents/${incidentId}/export`),
```

- [ ] **Step 2: Replace Incidents page with workspace**

Update `frontend/src/pages/IncidentsPage.tsx` to:

- keep `incidents`, `selectedId`, `detail`, `similar`, `exportPreview`, and `error` state.
- load list on mount.
- load detail and similar when selecting an Incident.
- render filters as native `select` controls for status and severity.
- render timeline rows with `event_type`, `summary`, `source`, and `occurred_at`.
- render latest RCA Markdown in a `pre` block.
- provide buttons for `生成 RCA` and `导出 Markdown`.

Use existing `panel`, `panel-heading`, `table-list`, `table-row`, and `muted` classes to stay consistent with M4 styling.

- [ ] **Step 3: Run frontend typecheck**

Run:

```bash
cd frontend && npm run typecheck
```

Expected: TypeScript completes with no errors.

- [ ] **Step 4: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: Vite build completes and writes ignored `frontend/dist/`.

- [ ] **Step 5: Commit frontend workspace**

```bash
git add frontend/src/api/types.ts frontend/src/api/client.ts frontend/src/pages/IncidentsPage.tsx
git commit -m "feat: 增加Incident事件工作台"
```

---

### Task 8: Documentation, Status, and Final Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/PROJECT_STATUS.md`

- [ ] **Step 1: Document M5 local usage**

Add a README section:

````markdown
## M5 事件记忆与 RCA

M5 不需要打开云实例即可本地开发和验证。使用本地 SQLite 与 Alertmanager fixture 即可验证 Incident 自动建档、时间线、历史检索和 RCA 导出。

```bash
DATASENTRY_LLM_PROVIDER=mock .venv/bin/uvicorn datasentry.api:create_app --factory --host 127.0.0.1 --port 8000
curl -X POST http://127.0.0.1:8000/api/alertmanager/webhook \
  -H 'Content-Type: application/json' \
  --data @tests/fixtures/alertmanager/kline_freshness_firing.json
```

生产边界保持不变：M5 只执行只读诊断和本地事件记忆写入，不执行生产写操作，不读取 MySQL 异常表 `RECOVER_YOUR_DATA_info` 内容，不引入任意 Shell 或 RAG。
````

- [ ] **Step 2: Update project status**

In `docs/PROJECT_STATUS.md`:

- change M5 stage to `实施中` while work is active.
- after final verification, record passed commands and whether cloud smoke was skipped or run.
- preserve the current snapshot plus key changelog structure.

- [ ] **Step 3: Run full backend verification**

Run:

```bash
.venv/bin/ruff format --check .
.venv/bin/ruff check .
.venv/bin/mypy src
.venv/bin/pytest tests -q -W error::ResourceWarning --cov=datasentry --cov-report=term-missing --cov-fail-under=90
```

Expected:

- Ruff format passes.
- Ruff lint passes.
- mypy passes.
- pytest passes with coverage at or above 90%.

- [ ] **Step 4: Run full frontend verification**

Run:

```bash
cd frontend && npm run typecheck
cd frontend && npm run build
```

Expected:

- TypeScript typecheck passes.
- Vite build passes.

- [ ] **Step 5: Optional cloud smoke decision**

If the user opens the cloud instance, run a read-only smoke by posting a representative Alertmanager payload to the local DataSentry API and viewing the Incident workspace. If the cloud instance is not open, record:

```text
云实例未打开；M5 已完成本地 fixture、API、Repository、RCA 和前端构建验证，真实 Alertmanager smoke 留作后续只读验收。
```

- [ ] **Step 6: Commit documentation and final status**

```bash
git add README.md docs/PROJECT_STATUS.md
git commit -m "docs: 记录M5事件记忆使用方式"
```

---

## Final Integration Checklist

- [ ] Run `git status --short --branch` and confirm only intentional changes remain.
- [ ] Run `git log --oneline -8` and list M5 commit hashes.
- [ ] Confirm no new secrets appear in tracked files:

```bash
git diff --cached
rg -n "AKIA|SECRET|TOKEN|PASSWORD|PRIVATE KEY|Authorization|Cookie" README.md docs src tests frontend/src
```

- [ ] If pushing, first run:

```bash
git fetch origin
git status --short --branch
```

If local branch diverges from `origin/main`, stop and report instead of pushing.

## Plan Self-Review

- Spec coverage: Tasks cover Incident lifecycle, Alertmanager upsert, timeline persistence, links, fingerprints, similar search, RCA Markdown, API endpoints, React workspace, docs, SQLite to PostgreSQL evaluation note, and final verification.
- Placeholder scan: The plan intentionally contains no TBD/TODO placeholders and no unspecified external service dependencies.
- Type consistency: `IncidentLink`, `IncidentTimelineEvent`, `IncidentFingerprint`, `IncidentRCAReport`, `IncidentDetail`, and `IncidentUpsertResult` names are used consistently across Python models, Repository methods, API responses, and frontend types.
