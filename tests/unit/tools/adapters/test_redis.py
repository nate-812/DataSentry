from datetime import UTC, datetime

from datasentry.tools.adapters.redis import RedisKeySampleTool, _decode

NOW = datetime(2026, 6, 25, 12, 0, tzinfo=UTC)


class FakeClient:
    def info(self) -> dict[str, object]:
        return {"redis_version": "7.2", "used_memory": 1024}

    def dbsize(self) -> int:
        return 2

    def scan(
        self,
        cursor: int,
        *,
        match: str,
        count: int,
    ) -> tuple[int, list[bytes]]:
        del cursor, match, count
        return 0, [b"risk:blacklist:BTCUSDT"]

    def type(self, key: str) -> bytes:
        del key
        return b"string"

    def ttl(self, key: str) -> int:
        del key
        return 3600

    def get(self, key: str) -> bytes:
        del key
        return b"password=secret"

    def __enter__(self) -> "FakeClient":
        return self

    def __exit__(self, *args: object) -> None:
        del args


class FakeTransport:
    def client(self, target: str) -> FakeClient:
        del target
        return FakeClient()


def _fact(observations: list, metric: str):
    return next(item for item in observations if item.metric_or_fact == metric)


def test_redis_key_sample_is_bounded_and_redacted() -> None:
    observations = RedisKeySampleTool(
        FakeTransport(),
        clock=lambda: NOW,
    ).execute(
        inspection_id="inspection-1",
        target="redis",
        arguments={"pattern": "risk:blacklist:*", "limit": 20},
    )

    assert _fact(observations, "redis_dbsize").value == 2
    sample = _fact(observations, "redis_key_sample").value
    assert sample == [
        {
            "key": "risk:blacklist:BTCUSDT",
            "type": "string",
            "ttl_seconds": 3600,
            "value": "password=[REDACTED]",
        }
    ]


def test_redis_value_decoder_reports_large_or_binary_values() -> None:
    assert _decode(b"x" * 2049) == {"binary": True, "byte_count": 2049}
    assert _decode(b"\xff") == {"binary": True, "byte_count": 1}
    assert _decode(None) is None
