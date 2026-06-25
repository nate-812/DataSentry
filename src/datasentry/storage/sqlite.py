"""DataSentry Repository 的 SQLite 实现。"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Self

from pydantic import JsonValue, TypeAdapter

from datasentry.domain import (
    Evidence,
    Finding,
    Incident,
    Inspection,
    Observation,
    Operation,
)
from datasentry.errors import NotFoundError, StorageError
from datasentry.storage.migrations import connect, upgrade_database
from datasentry.storage.repository import InspectionAggregate

EVIDENCE_LIST_ADAPTER = TypeAdapter(list[Evidence])
STRING_LIST_ADAPTER = TypeAdapter(list[str])
JSON_VALUE_ADAPTER: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)
JSON_OBJECT_ADAPTER = TypeAdapter(dict[str, JsonValue])


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

    def add_observation(self, observation: Observation) -> None:
        connection = self._require_open()
        try:
            with connection:
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
        except sqlite3.IntegrityError as error:
            raise self._integrity_error(error) from error

    def add_finding(self, finding: Finding) -> None:
        connection = self._require_open()
        try:
            with connection:
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
                        _dump_json(
                            [evidence.model_dump(mode="json") for evidence in finding.evidence]
                        ),
                        finding.impact,
                        finding.recommendation,
                        _dump_json(finding.unknowns),
                        _dump_datetime(finding.created_at),
                    ),
                )
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
