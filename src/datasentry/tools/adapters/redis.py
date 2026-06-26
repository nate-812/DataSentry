"""Redis INFO、DBSIZE、受限 SCAN 和小样本读取。"""

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Literal, Protocol, cast

from pydantic import BaseModel, Field, JsonValue, ValidationError

from datasentry.domain import Observation, ToolName
from datasentry.domain.common import utc_now
from datasentry.tools.errors import ToolError
from datasentry.tools.redaction import redact_text
from datasentry.tools.transports.redis import ReadOnlyRedisClient


class RedisReadTransport(Protocol):
    def client(self, target: str) -> ReadOnlyRedisClient:
        raise NotImplementedError  # pragma: no cover


class RedisSampleArguments(BaseModel):
    pattern: Literal["risk:blacklist:*"]
    limit: int = Field(default=20, ge=1, le=100)


def _decode(value: bytes | None, *, max_bytes: int = 2048) -> JsonValue:
    if value is None:
        return None
    if len(value) > max_bytes:
        return {"binary": True, "byte_count": len(value)}
    try:
        return redact_text(value.decode("utf-8"))
    except UnicodeDecodeError:
        return {"binary": True, "byte_count": len(value)}


class RedisKeySampleTool:
    name = ToolName.GET_REDIS_KEY_SAMPLE

    def __init__(
        self,
        transport: RedisReadTransport,
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
            parsed = RedisSampleArguments.model_validate(arguments)
        except ValidationError as error:
            raise ToolError(
                code="tool.invalid_arguments",
                message="Redis 样本参数无效",
            ) from error
        samples: list[JsonValue] = []
        with self._transport.client(target) as client:
            info = client.info()
            database_size = client.dbsize()
            cursor = 0
            batches = 0
            while len(samples) < parsed.limit and batches < 10:
                cursor, keys = client.scan(
                    cursor,
                    match=parsed.pattern,
                    count=min(parsed.limit, 100),
                )
                batches += 1
                for raw_key in keys:
                    if len(samples) >= parsed.limit:
                        break
                    try:
                        key = raw_key.decode("utf-8")
                    except UnicodeDecodeError:
                        continue
                    key_type = client.type(key).decode("ascii", errors="replace")
                    value = client.get(key) if key_type == "string" else None
                    samples.append(
                        {
                            "key": key,
                            "type": key_type,
                            "ttl_seconds": client.ttl(key),
                            "value": _decode(value),
                        }
                    )
                if cursor == 0:
                    break
        observed_at = self._clock()
        return [
            Observation(
                inspection_id=inspection_id,
                component="redis",
                metric_or_fact="redis_info",
                value=cast(JsonValue, info),
                source="redis_readonly",
                target=target,
                observed_at=observed_at,
            ),
            Observation(
                inspection_id=inspection_id,
                component="redis",
                metric_or_fact="redis_dbsize",
                value=database_size,
                source="redis_readonly",
                target=target,
                observed_at=observed_at,
            ),
            Observation(
                inspection_id=inspection_id,
                component="redis",
                metric_or_fact="redis_key_sample",
                value=samples,
                source="redis_readonly",
                target=parsed.pattern,
                observed_at=observed_at,
            ),
        ]
