"""Doris 固定业务表数据新鲜度查询。"""

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Literal, Protocol

from pydantic import BaseModel, JsonValue, ValidationError

from datasentry.domain import Observation, ToolName
from datasentry.domain.common import utc_now
from datasentry.tools.errors import ToolError
from datasentry.tools.transports.mysql import ReadOnlyQuery

TABLE_QUERIES = {
    "kline_1min": (ReadOnlyQuery.DORIS_KLINE_FRESHNESS, "kline"),
    "whale_alert": (ReadOnlyQuery.DORIS_WHALE_FRESHNESS, "whale"),
    "risk_trigger": (ReadOnlyQuery.DORIS_RISK_FRESHNESS, "risk"),
    "ai_diagnosis": (ReadOnlyQuery.DORIS_AI_FRESHNESS, "ai_diagnosis"),
}


class MySqlReadTransport(Protocol):
    def fetch_all(
        self,
        target: str,
        query: ReadOnlyQuery,
        parameters: tuple[object, ...],
    ) -> list[dict[str, JsonValue]]:
        raise NotImplementedError  # pragma: no cover


class FreshnessArguments(BaseModel):
    table: Literal["kline_1min", "whale_alert", "risk_trigger", "ai_diagnosis"]


def _aware(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise ToolError(
            code="tool.parse_failed",
            message="Doris 时间字段无法解析",
        )
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class DorisFreshnessTool:
    name = ToolName.GET_DORIS_TABLE_FRESHNESS

    def __init__(
        self,
        transport: MySqlReadTransport,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._transport = transport
        self._clock = clock

    def execute(
        self,
        *,
        inspection_id: str,
        target: str,
        arguments: Mapping[str, JsonValue],
    ) -> list[Observation]:
        try:
            table = FreshnessArguments.model_validate(arguments).table
        except ValidationError as error:
            raise ToolError(
                code="tool.invalid_arguments",
                message="Doris 表参数无效",
            ) from error
        query, prefix = TABLE_QUERIES[table]
        rows = self._transport.fetch_all(target, query, ())
        if len(rows) != 1:
            raise ToolError(
                code="tool.parse_failed",
                message="Doris 新鲜度查询返回行数无效",
            )
        latest = _aware(rows[0].get("latest_event_time"))
        database_now = _aware(rows[0].get("database_now")) or self._clock()
        freshness: JsonValue = None
        clock_skew: JsonValue = None
        if latest is not None:
            difference = (database_now - latest).total_seconds()
            if difference >= 0:
                freshness = int(difference)
            else:
                clock_skew = int(abs(difference))
        observed_at = self._clock()
        values: list[tuple[str, JsonValue]] = [
            (
                f"{prefix}_latest_event_time",
                None if latest is None else latest.isoformat(),
            ),
            (f"{prefix}_freshness_seconds", freshness),
        ]
        if clock_skew is not None:
            values.append((f"{prefix}_clock_skew_seconds", clock_skew))
        return [
            Observation(
                inspection_id=inspection_id,
                component="doris",
                metric_or_fact=metric,
                value=value,
                source="doris_readonly",
                target=table,
                observed_at=observed_at,
            )
            for metric, value in values
        ]
