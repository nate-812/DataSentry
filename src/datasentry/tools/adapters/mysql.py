"""MySQL 规则表的受限样本查询。"""

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Literal, Protocol, cast

from pydantic import BaseModel, Field, JsonValue, ValidationError

from datasentry.domain import Observation, ToolName
from datasentry.domain.common import utc_now
from datasentry.tools.errors import ToolError
from datasentry.tools.transports.mysql import ReadOnlyQuery

TABLE_QUERIES = {
    "whale_thresholds": ReadOnlyQuery.MYSQL_WHALE_THRESHOLDS,
    "risk_rules": ReadOnlyQuery.MYSQL_RISK_RULES,
}


class MySqlReadTransport(Protocol):
    def fetch_all(
        self,
        target: str,
        query: ReadOnlyQuery,
        parameters: tuple[object, ...],
    ) -> list[dict[str, JsonValue]]:
        raise NotImplementedError  # pragma: no cover


class SampleArguments(BaseModel):
    table: Literal["whale_thresholds", "risk_rules"]
    limit: int = Field(default=20, ge=1, le=100)


class MySqlTableSampleTool:
    name = ToolName.GET_MYSQL_TABLE_SAMPLE

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
            parsed = SampleArguments.model_validate(arguments)
        except ValidationError as error:
            raise ToolError(
                code="tool.invalid_arguments",
                message="MySQL 样本参数无效",
            ) from error
        rows = self._transport.fetch_all(
            target,
            TABLE_QUERIES[parsed.table],
            (parsed.limit,),
        )
        return [
            Observation(
                inspection_id=inspection_id,
                component="mysql",
                metric_or_fact="mysql_table_sample",
                value={
                    "table": parsed.table,
                    "rows": cast(JsonValue, rows[: parsed.limit]),
                    "limit": parsed.limit,
                },
                source="mysql_readonly",
                target=parsed.table,
                observed_at=self._clock(),
            )
        ]
