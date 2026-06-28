"""DataSentry Repository 的 SQLite 实现。"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Self

from pydantic import JsonValue, TypeAdapter

from datasentry.chat import (
    ChatEventType,
    ChatMessage,
    ChatRole,
    ChatRun,
    ChatRunStatus,
    ChatSession,
)
from datasentry.domain import (
    Evidence,
    Finding,
    Incident,
    Inspection,
    Observation,
    Operation,
    ToolInvocation,
)
from datasentry.domain.enums import IncidentStatus, InspectionStatus, OperationStatus
from datasentry.errors import NotFoundError, StorageError
from datasentry.storage.migrations import connect, upgrade_database
from datasentry.storage.repository import InspectionAggregate

EVIDENCE_LIST_ADAPTER = TypeAdapter(list[Evidence])
STRING_LIST_ADAPTER = TypeAdapter(list[str])
JSON_VALUE_ADAPTER: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)
JSON_OBJECT_ADAPTER = TypeAdapter(dict[str, JsonValue])
MAX_LIST_LIMIT = 100


def _dump_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _load_json(value: str) -> object:
    return json.loads(value)


def _dump_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _load_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def _load_required_datetime(value: str | None) -> datetime:
    loaded = _load_datetime(value)
    if loaded is None:
        raise StorageError(
            code="storage.invalid_data",
            message="数据库中的时间字段缺失",
        )
    return loaded


class SQLiteRepository:
    """将不可变领域快照持久化到本地 SQLite。"""

    def __init__(self, database_path: Path) -> None:
        upgrade_database(database_path)
        self._connection = connect(database_path)
        self._closed = False

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc, traceback
        self.close()

    def save_inspection(self, inspection: Inspection) -> None:
        connection = self._require_open()
        try:
            with connection:
                connection.execute(
                    """
                    INSERT INTO inspections (
                        id, question, scope_json, status, summary,
                        started_at, finished_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        inspection.id,
                        inspection.question,
                        _dump_json(inspection.scope),
                        inspection.status.value,
                        inspection.summary,
                        _dump_datetime(inspection.started_at),
                        _dump_datetime(inspection.finished_at),
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise self._integrity_error(error) from error

    def start_inspection(self, inspection: Inspection) -> None:
        """插入一条运行中的巡检记录。"""
        if inspection.status is not InspectionStatus.RUNNING:
            raise self._invalid_inspection_transition()
        self.save_inspection(inspection)

    def complete_inspection(
        self,
        inspection: Inspection,
        observations: list[Observation],
        findings: list[Finding],
    ) -> InspectionAggregate:
        """原子更新巡检并写入全部 Observation 与 Finding。"""
        if inspection.status is not InspectionStatus.COMPLETED:
            raise self._invalid_inspection_transition()
        self._validate_children(inspection, observations, findings)
        connection = self._require_open()
        try:
            with connection:
                self._update_running_inspection(connection, inspection)
                for observation in observations:
                    self._insert_observation(connection, observation)
                for finding in findings:
                    self._insert_finding(connection, finding)
        except sqlite3.IntegrityError as error:
            raise self._integrity_error(error) from error
        return self.get_inspection(inspection.id)

    def fail_inspection(self, inspection: Inspection) -> None:
        """将运行中的巡检更新为失败状态。"""
        if inspection.status is not InspectionStatus.FAILED:
            raise self._invalid_inspection_transition()
        connection = self._require_open()
        with connection:
            self._update_running_inspection(connection, inspection)

    def add_observation(self, observation: Observation) -> None:
        connection = self._require_open()
        try:
            with connection:
                self._insert_observation(connection, observation)
        except sqlite3.IntegrityError as error:
            raise self._integrity_error(error) from error

    def add_finding(self, finding: Finding) -> None:
        connection = self._require_open()
        try:
            with connection:
                self._insert_finding(connection, finding)
        except sqlite3.IntegrityError as error:
            raise self._integrity_error(error) from error

    def get_inspection(self, inspection_id: str) -> InspectionAggregate:
        connection = self._require_open()
        inspection_row = connection.execute(
            "SELECT * FROM inspections WHERE id = ?",
            (inspection_id,),
        ).fetchone()
        if inspection_row is None:
            raise NotFoundError(
                code="storage.inspection_not_found",
                message="未找到指定巡检记录",
                details={"inspection_id": inspection_id},
            )
        observation_rows = connection.execute(
            """
            SELECT * FROM observations
            WHERE inspection_id = ?
            ORDER BY observed_at, id
            """,
            (inspection_id,),
        ).fetchall()
        finding_rows = connection.execute(
            """
            SELECT * FROM findings
            WHERE inspection_id = ?
            ORDER BY created_at, id
            """,
            (inspection_id,),
        ).fetchall()
        return InspectionAggregate(
            inspection=self._row_to_inspection(inspection_row),
            observations=[self._row_to_observation(row) for row in observation_rows],
            findings=[self._row_to_finding(row) for row in finding_rows],
        )

    def list_inspections(self, limit: int = 20) -> list[InspectionAggregate]:
        limit = self._validate_list_limit(limit)
        connection = self._require_open()
        rows = connection.execute(
            """
            SELECT id FROM inspections
            ORDER BY started_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [self.get_inspection(row["id"]) for row in rows]

    def save_tool_invocation(self, invocation: ToolInvocation) -> None:
        """保存已脱敏的工具调用审计。"""
        connection = self._require_open()
        try:
            with connection:
                connection.execute(
                    """
                    INSERT INTO tool_invocations (
                        id, inspection_id, tool_name, target, parameters_json,
                        status, observation_count, error_code, error_message,
                        started_at, finished_at, duration_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        invocation.id,
                        invocation.inspection_id,
                        invocation.tool_name.value,
                        invocation.target,
                        _dump_json(invocation.parameters),
                        invocation.status.value,
                        invocation.observation_count,
                        invocation.error_code,
                        invocation.error_message,
                        _dump_datetime(invocation.started_at),
                        _dump_datetime(invocation.finished_at),
                        invocation.duration_ms,
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise self._integrity_error(error) from error

    def list_tool_invocations(self, inspection_id: str) -> list[ToolInvocation]:
        """返回指定巡检的工具调用审计。"""
        connection = self._require_open()
        rows = connection.execute(
            """
            SELECT * FROM tool_invocations
            WHERE inspection_id = ?
            ORDER BY started_at, id
            """,
            (inspection_id,),
        ).fetchall()
        return [self._row_to_tool_invocation(row) for row in rows]

    def save_incident(self, incident: Incident) -> None:
        connection = self._require_open()
        try:
            with connection:
                connection.execute(
                    """
                    INSERT INTO incidents (
                        id, title, symptom, status, severity, root_cause,
                        opened_at, updated_at, resolved_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    self._incident_values(incident),
                )
        except sqlite3.IntegrityError as error:
            raise self._integrity_error(error) from error

    def update_incident(self, incident: Incident) -> None:
        connection = self._require_open()
        with connection:
            cursor = connection.execute(
                """
                UPDATE incidents SET
                    title = ?, symptom = ?, status = ?, severity = ?,
                    root_cause = ?, opened_at = ?, updated_at = ?, resolved_at = ?
                WHERE id = ?
                """,
                (
                    incident.title,
                    incident.symptom,
                    incident.status.value,
                    incident.severity.value,
                    incident.root_cause,
                    _dump_datetime(incident.opened_at),
                    _dump_datetime(incident.updated_at),
                    _dump_datetime(incident.resolved_at),
                    incident.id,
                ),
            )
        if cursor.rowcount == 0:
            raise NotFoundError(
                code="storage.incident_not_found",
                message="未找到指定 Incident",
                details={"incident_id": incident.id},
            )

    def get_incident(self, incident_id: str) -> Incident:
        connection = self._require_open()
        row = connection.execute(
            "SELECT * FROM incidents WHERE id = ?",
            (incident_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(
                code="storage.incident_not_found",
                message="未找到指定 Incident",
                details={"incident_id": incident_id},
            )
        return self._row_to_incident(row)

    def list_incidents(
        self,
        *,
        status: IncidentStatus | None = None,
        limit: int = 20,
    ) -> list[Incident]:
        limit = self._validate_list_limit(limit)
        connection = self._require_open()
        if status is None:
            rows = connection.execute(
                """
                SELECT * FROM incidents
                ORDER BY updated_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT * FROM incidents
                WHERE status = ?
                ORDER BY updated_at DESC, id DESC
                LIMIT ?
                """,
                (status.value, limit),
            ).fetchall()
        return [self._row_to_incident(row) for row in rows]

    def save_operation(self, operation: Operation) -> None:
        connection = self._require_open()
        try:
            with connection:
                connection.execute(
                    """
                    INSERT INTO operations (
                        id, incident_id, name, version, parameters_json,
                        risk, status, requester, approver, result_json,
                        requested_at, approved_at, executed_at, verified_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    self._operation_values(operation),
                )
        except sqlite3.IntegrityError as error:
            raise self._integrity_error(error) from error

    def update_operation(self, operation: Operation) -> None:
        connection = self._require_open()
        try:
            with connection:
                cursor = connection.execute(
                    """
                    UPDATE operations SET
                        incident_id = ?, name = ?, version = ?, parameters_json = ?,
                        risk = ?, status = ?, requester = ?, approver = ?,
                        result_json = ?, requested_at = ?, approved_at = ?,
                        executed_at = ?, verified_at = ?
                    WHERE id = ?
                    """,
                    (*self._operation_values(operation)[1:], operation.id),
                )
        except sqlite3.IntegrityError as error:
            raise self._integrity_error(error) from error
        if cursor.rowcount == 0:
            raise NotFoundError(
                code="storage.operation_not_found",
                message="未找到指定 Operation",
                details={"operation_id": operation.id},
            )

    def get_operation(self, operation_id: str) -> Operation:
        connection = self._require_open()
        row = connection.execute(
            "SELECT * FROM operations WHERE id = ?",
            (operation_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(
                code="storage.operation_not_found",
                message="未找到指定 Operation",
                details={"operation_id": operation_id},
            )
        return self._row_to_operation(row)

    def list_operations(
        self,
        *,
        status: OperationStatus | None = None,
        limit: int = 20,
    ) -> list[Operation]:
        limit = self._validate_list_limit(limit)
        connection = self._require_open()
        if status is None:
            rows = connection.execute(
                """
                SELECT * FROM operations
                ORDER BY requested_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT * FROM operations
                WHERE status = ?
                ORDER BY requested_at DESC, id DESC
                LIMIT ?
                """,
                (status.value, limit),
            ).fetchall()
        return [self._row_to_operation(row) for row in rows]

    def save_chat_session(self, session: ChatSession) -> None:
        connection = self._require_open()
        try:
            with connection:
                connection.execute(
                    """
                    INSERT INTO chat_sessions (
                        id, title, created_at, updated_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        session.id,
                        session.title,
                        _dump_datetime(session.created_at),
                        _dump_datetime(session.updated_at),
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise self._integrity_error(error) from error

    def get_chat_session(self, session_id: str) -> ChatSession:
        connection = self._require_open()
        row = connection.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM chat_sessions
            WHERE id = ?
            """,
            (session_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(
                code="storage.chat_session_not_found",
                message="未找到指定聊天会话",
                details={"session_id": session_id},
            )
        return self._row_to_chat_session(row)

    def list_chat_sessions(self, limit: int = 20) -> list[ChatSession]:
        limit = self._validate_list_limit(limit)
        connection = self._require_open()
        rows = connection.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM chat_sessions
            ORDER BY updated_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [self._row_to_chat_session(row) for row in rows]

    def save_chat_message(self, message: ChatMessage) -> None:
        connection = self._require_open()
        try:
            with connection:
                connection.execute(
                    """
                    INSERT INTO chat_messages (
                        id, session_id, role, content, inspection_id,
                        llm_status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        message.id,
                        message.session_id,
                        message.role.value,
                        message.content,
                        message.inspection_id,
                        message.llm_status,
                        _dump_datetime(message.created_at),
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise self._integrity_error(error) from error

    def list_chat_messages(self, session_id: str, limit: int = 20) -> list[ChatMessage]:
        limit = self._validate_list_limit(limit)
        connection = self._require_open()
        rows = connection.execute(
            """
            SELECT id, session_id, role, content, inspection_id, llm_status, created_at
            FROM chat_messages
            WHERE session_id = ?
            ORDER BY created_at, id
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
        return [self._row_to_chat_message(row) for row in rows]

    def save_chat_run(self, run: ChatRun) -> None:
        connection = self._require_open()
        try:
            with connection:
                connection.execute(
                    """
                    INSERT INTO chat_runs (
                        id, session_id, user_message_id, status, inspection_id,
                        error_code, error_message, created_at, finished_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    self._chat_run_values(run),
                )
        except sqlite3.IntegrityError as error:
            raise self._integrity_error(error) from error

    def update_chat_run(self, run: ChatRun) -> None:
        connection = self._require_open()
        try:
            with connection:
                cursor = connection.execute(
                    """
                    UPDATE chat_runs SET
                        status = ?, inspection_id = ?, error_code = ?,
                        error_message = ?, finished_at = ?
                    WHERE id = ?
                    """,
                    (
                        run.status.value,
                        run.inspection_id,
                        run.error_code,
                        run.error_message,
                        _dump_datetime(run.finished_at),
                        run.id,
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise self._integrity_error(error) from error
        if cursor.rowcount == 0:
            raise NotFoundError(
                code="storage.chat_run_not_found",
                message="未找到指定聊天任务",
                details={"run_id": run.id},
            )

    def get_chat_run(self, run_id: str) -> ChatRun:
        connection = self._require_open()
        row = connection.execute(
            """
            SELECT
                id, session_id, user_message_id, status, inspection_id,
                error_code, error_message, created_at, finished_at
            FROM chat_runs
            WHERE id = ?
            """,
            (run_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(
                code="storage.chat_run_not_found",
                message="未找到指定聊天任务",
                details={"run_id": run_id},
            )
        return self._row_to_chat_run(row)

    def save_chat_run_event(self, event: ChatRun.Event) -> None:
        connection = self._require_open()
        try:
            with connection:
                connection.execute(
                    """
                    INSERT INTO chat_run_events (
                        id, run_id, event_type, payload_json, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        event.id,
                        event.run_id,
                        event.event_type.value,
                        _dump_json(event.payload),
                        _dump_datetime(event.created_at),
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise self._integrity_error(error) from error

    def list_chat_run_events(self, run_id: str, limit: int = 100) -> list[ChatRun.Event]:
        limit = self._validate_list_limit(limit)
        connection = self._require_open()
        rows = connection.execute(
            """
            SELECT id, run_id, event_type, payload_json, created_at
            FROM chat_run_events
            WHERE run_id = ?
            ORDER BY created_at, id
            LIMIT ?
            """,
            (run_id, limit),
        ).fetchall()
        return [self._row_to_chat_run_event(row) for row in rows]

    def close(self) -> None:
        if not self._closed:
            self._connection.close()
            self._closed = True

    def _require_open(self) -> sqlite3.Connection:
        if self._closed:
            raise StorageError(
                code="storage.closed",
                message="Repository 已关闭",
            )
        return self._connection

    @staticmethod
    def _invalid_inspection_transition() -> StorageError:
        return StorageError(
            code="storage.invalid_inspection_transition",
            message="巡检状态转换无效",
        )

    @staticmethod
    def _validate_list_limit(limit: int) -> int:
        if not 1 <= limit <= MAX_LIST_LIMIT:
            raise StorageError(
                code="storage.invalid_limit",
                message=f"列表查询 limit 必须在 1 到 {MAX_LIST_LIMIT} 之间",
                details={"limit": limit, "max_limit": MAX_LIST_LIMIT},
            )
        return limit

    @classmethod
    def _update_running_inspection(
        cls,
        connection: sqlite3.Connection,
        inspection: Inspection,
    ) -> None:
        cursor = connection.execute(
            """
            UPDATE inspections SET
                question = ?, scope_json = ?, status = ?, summary = ?,
                started_at = ?, finished_at = ?
            WHERE id = ? AND status = 'running'
            """,
            (
                inspection.question,
                _dump_json(inspection.scope),
                inspection.status.value,
                inspection.summary,
                _dump_datetime(inspection.started_at),
                _dump_datetime(inspection.finished_at),
                inspection.id,
            ),
        )
        if cursor.rowcount == 0:
            raise cls._invalid_inspection_transition()

    @staticmethod
    def _validate_children(
        inspection: Inspection,
        observations: list[Observation],
        findings: list[Finding],
    ) -> None:
        invalid_observation = any(item.inspection_id != inspection.id for item in observations)
        invalid_finding = any(item.inspection_id != inspection.id for item in findings)
        if invalid_observation or invalid_finding:
            raise StorageError(
                code="storage.invalid_inspection_child",
                message="巡检子记录引用了不同的巡检 ID",
            )

    @staticmethod
    def _insert_observation(
        connection: sqlite3.Connection,
        observation: Observation,
    ) -> None:
        connection.execute(
            """
            INSERT INTO observations (
                id, inspection_id, component, metric_or_fact,
                value_json, source, target, observed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                observation.id,
                observation.inspection_id,
                observation.component,
                observation.metric_or_fact,
                _dump_json(observation.value),
                observation.source,
                observation.target,
                _dump_datetime(observation.observed_at),
            ),
        )

    @staticmethod
    def _insert_finding(
        connection: sqlite3.Connection,
        finding: Finding,
    ) -> None:
        connection.execute(
            """
            INSERT INTO findings (
                id, inspection_id, severity, status, claim,
                evidence_json, impact, recommendation,
                unknowns_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                finding.id,
                finding.inspection_id,
                finding.severity.value,
                finding.status.value,
                finding.claim,
                _dump_json([evidence.model_dump(mode="json") for evidence in finding.evidence]),
                finding.impact,
                finding.recommendation,
                _dump_json(finding.unknowns),
                _dump_datetime(finding.created_at),
            ),
        )

    @staticmethod
    def _integrity_error(error: sqlite3.IntegrityError) -> StorageError:
        message = str(error).lower()
        if "unique constraint failed" in message:
            code = "storage.conflict"
            safe_message = "已存在相同 ID 的记录"
        else:
            code = "storage.constraint"
            safe_message = "数据违反存储约束"
        return StorageError(code=code, message=safe_message)

    @staticmethod
    def _incident_values(incident: Incident) -> tuple[object, ...]:
        return (
            incident.id,
            incident.title,
            incident.symptom,
            incident.status.value,
            incident.severity.value,
            incident.root_cause,
            _dump_datetime(incident.opened_at),
            _dump_datetime(incident.updated_at),
            _dump_datetime(incident.resolved_at),
        )

    @staticmethod
    def _operation_values(operation: Operation) -> tuple[object, ...]:
        return (
            operation.id,
            operation.incident_id,
            operation.name,
            operation.version,
            _dump_json(operation.parameters),
            operation.risk.value,
            operation.status.value,
            operation.requester,
            operation.approver,
            None if operation.result is None else _dump_json(operation.result),
            _dump_datetime(operation.requested_at),
            _dump_datetime(operation.approved_at),
            _dump_datetime(operation.executed_at),
            _dump_datetime(operation.verified_at),
        )

    @staticmethod
    def _chat_run_values(run: ChatRun) -> tuple[object, ...]:
        return (
            run.id,
            run.session_id,
            run.user_message_id,
            run.status.value,
            run.inspection_id,
            run.error_code,
            run.error_message,
            _dump_datetime(run.created_at),
            _dump_datetime(run.finished_at),
        )

    @staticmethod
    def _row_to_inspection(row: sqlite3.Row) -> Inspection:
        return Inspection(
            id=row["id"],
            question=row["question"],
            scope=STRING_LIST_ADAPTER.validate_python(_load_json(row["scope_json"])),
            status=row["status"],
            summary=row["summary"],
            started_at=_load_required_datetime(row["started_at"]),
            finished_at=_load_datetime(row["finished_at"]),
        )

    @staticmethod
    def _row_to_observation(row: sqlite3.Row) -> Observation:
        return Observation(
            id=row["id"],
            inspection_id=row["inspection_id"],
            component=row["component"],
            metric_or_fact=row["metric_or_fact"],
            value=JSON_VALUE_ADAPTER.validate_python(_load_json(row["value_json"])),
            source=row["source"],
            target=row["target"],
            observed_at=_load_required_datetime(row["observed_at"]),
        )

    @staticmethod
    def _row_to_finding(row: sqlite3.Row) -> Finding:
        evidence = EVIDENCE_LIST_ADAPTER.validate_python(_load_json(row["evidence_json"]))
        return Finding(
            id=row["id"],
            inspection_id=row["inspection_id"],
            severity=row["severity"],
            status=row["status"],
            claim=row["claim"],
            evidence=evidence,
            impact=row["impact"],
            recommendation=row["recommendation"],
            unknowns=STRING_LIST_ADAPTER.validate_python(_load_json(row["unknowns_json"])),
            created_at=_load_required_datetime(row["created_at"]),
        )

    @staticmethod
    def _row_to_incident(row: sqlite3.Row) -> Incident:
        return Incident(
            id=row["id"],
            title=row["title"],
            symptom=row["symptom"],
            status=row["status"],
            severity=row["severity"],
            root_cause=row["root_cause"],
            opened_at=_load_required_datetime(row["opened_at"]),
            updated_at=_load_required_datetime(row["updated_at"]),
            resolved_at=_load_datetime(row["resolved_at"]),
        )

    @staticmethod
    def _row_to_operation(row: sqlite3.Row) -> Operation:
        result_json = row["result_json"]
        return Operation(
            id=row["id"],
            incident_id=row["incident_id"],
            name=row["name"],
            version=row["version"],
            parameters=JSON_OBJECT_ADAPTER.validate_python(_load_json(row["parameters_json"])),
            risk=row["risk"],
            status=row["status"],
            requester=row["requester"],
            approver=row["approver"],
            result=(
                None
                if result_json is None
                else JSON_OBJECT_ADAPTER.validate_python(_load_json(result_json))
            ),
            requested_at=_load_required_datetime(row["requested_at"]),
            approved_at=_load_datetime(row["approved_at"]),
            executed_at=_load_datetime(row["executed_at"]),
            verified_at=_load_datetime(row["verified_at"]),
        )

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
        payload = JSON_OBJECT_ADAPTER.validate_python(_load_json(row["payload_json"]))
        return ChatRun.Event(
            id=row["id"],
            run_id=row["run_id"],
            event_type=ChatEventType(row["event_type"]),
            payload=payload,
            created_at=_load_required_datetime(row["created_at"]),
        )

    @staticmethod
    def _row_to_tool_invocation(row: sqlite3.Row) -> ToolInvocation:
        return ToolInvocation(
            id=row["id"],
            inspection_id=row["inspection_id"],
            tool_name=row["tool_name"],
            target=row["target"],
            parameters=JSON_OBJECT_ADAPTER.validate_python(_load_json(row["parameters_json"])),
            status=row["status"],
            observation_count=row["observation_count"],
            error_code=row["error_code"],
            error_message=row["error_message"],
            started_at=_load_required_datetime(row["started_at"]),
            finished_at=_load_required_datetime(row["finished_at"]),
            duration_ms=row["duration_ms"],
        )
