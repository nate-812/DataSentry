import pytest
from redis.exceptions import TimeoutError as RedisTimeoutError

from datasentry.tools.errors import ToolError
from datasentry.tools.targets import (
    EnvironmentSecretResolver,
    HostTarget,
    RedisTarget,
    ToolLimits,
)
from datasentry.tools.transports.redis import RedisTransport


class FakeRedis:
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
        return b"blocked"

    def close(self) -> None:
        return None


class TimeoutRedis(FakeRedis):
    def info(self) -> dict[str, object]:
        raise RedisTimeoutError("timeout")


def test_redis_transport_exposes_only_bounded_read_methods(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_REDIS_PASSWORD", "secret")
    transport = RedisTransport(
        hosts={"data1": HostTarget(address="192.0.2.10")},
        targets={
            "redis": RedisTarget(
                host="data1",
                port=6379,
                password_env="TEST_REDIS_PASSWORD",
            )
        },
        limits=ToolLimits(),
        secrets=EnvironmentSecretResolver(),
        client_factory=lambda **_: FakeRedis(),
    )

    with transport.client("redis") as client:
        assert client.info()["redis_version"] == "7.2"
        assert client.dbsize() == 2
        assert client.scan(0, match="risk:blacklist:*", count=20)[1] == [b"risk:blacklist:BTCUSDT"]
        assert not hasattr(client, "execute_command")


def test_redis_transport_reports_missing_secret_as_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TEST_REDIS_PASSWORD", raising=False)
    called = False

    def client_factory(**_: object) -> FakeRedis:
        nonlocal called
        called = True
        return FakeRedis()

    transport = RedisTransport(
        hosts={"data1": HostTarget(address="192.0.2.10")},
        targets={
            "redis": RedisTarget(
                host="data1",
                port=6379,
                password_env="TEST_REDIS_PASSWORD",
            )
        },
        limits=ToolLimits(),
        secrets=EnvironmentSecretResolver(),
        client_factory=client_factory,
    )

    with pytest.raises(ToolError) as raised:
        transport.client("redis")

    assert raised.value.code == "tool.configuration"
    assert called is False


def test_redis_read_client_converts_timeout_to_tool_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_REDIS_PASSWORD", "secret")
    transport = RedisTransport(
        hosts={"data1": HostTarget(address="192.0.2.10")},
        targets={
            "redis": RedisTarget(
                host="data1",
                port=6379,
                password_env="TEST_REDIS_PASSWORD",
            )
        },
        limits=ToolLimits(),
        secrets=EnvironmentSecretResolver(),
        client_factory=lambda **_: TimeoutRedis(),
    )

    with transport.client("redis") as client, pytest.raises(ToolError) as raised:
        client.info()

    assert raised.value.code == "tool.timeout"
    assert raised.value.retryable is True
