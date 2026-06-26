"""只暴露有限 Redis 读命令的传输包装。"""

from collections.abc import Callable, Mapping
from types import TracebackType
from typing import Protocol, Self, TypeVar, cast

import redis
from redis.exceptions import (
    AuthenticationError as RedisAuthenticationError,
)
from redis.exceptions import (
    ConnectionError as RedisConnectionError,
)
from redis.exceptions import (
    RedisError,
)
from redis.exceptions import (
    TimeoutError as RedisTimeoutError,
)

from datasentry.errors import ConfigurationError
from datasentry.tools.errors import ToolError
from datasentry.tools.targets import (
    EnvironmentSecretResolver,
    HostTarget,
    RedisTarget,
    ToolLimits,
)


class RedisProtocol(Protocol):
    def info(self) -> dict[str, object]:
        raise NotImplementedError  # pragma: no cover

    def dbsize(self) -> int:
        raise NotImplementedError  # pragma: no cover

    def scan(
        self,
        cursor: int,
        *,
        match: str,
        count: int,
    ) -> tuple[int, list[bytes]]:
        raise NotImplementedError  # pragma: no cover

    def type(self, key: str) -> bytes:
        raise NotImplementedError  # pragma: no cover

    def ttl(self, key: str) -> int:
        raise NotImplementedError  # pragma: no cover

    def get(self, key: str) -> bytes | None:
        raise NotImplementedError  # pragma: no cover

    def close(self) -> None:
        raise NotImplementedError  # pragma: no cover


RedisFactory = Callable[..., RedisProtocol]
DEFAULT_REDIS_FACTORY = cast(RedisFactory, redis.Redis)
T = TypeVar("T")


class ReadOnlyRedisClient:
    """没有通用命令入口的 Redis 只读客户端。"""

    def __init__(self, client: RedisProtocol) -> None:
        self._client = client

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc, traceback
        self._client.close()

    def info(self) -> dict[str, object]:
        return self._read(self._client.info)

    def dbsize(self) -> int:
        return self._read(self._client.dbsize)

    def scan(
        self,
        cursor: int,
        *,
        match: str,
        count: int,
    ) -> tuple[int, list[bytes]]:
        return self._read(
            self._client.scan,
            cursor,
            match=match,
            count=count,
        )

    def type(self, key: str) -> bytes:
        return self._read(self._client.type, key)

    def ttl(self, key: str) -> int:
        return self._read(self._client.ttl, key)

    def get(self, key: str) -> bytes | None:
        return self._read(self._client.get, key)

    @staticmethod
    def _read(
        operation: Callable[..., T],
        *args: object,
        **kwargs: object,
    ) -> T:
        try:
            return operation(*args, **kwargs)
        except RedisAuthenticationError as error:
            raise ToolError(
                code="tool.authentication_failed",
                message="Redis 认证失败",
            ) from error
        except RedisTimeoutError as error:
            raise ToolError(
                code="tool.timeout",
                message="Redis 只读查询超时",
                retryable=True,
            ) from error
        except RedisConnectionError as error:
            raise ToolError(
                code="tool.connection_failed",
                message="Redis 连接失败",
                retryable=True,
            ) from error
        except RedisError as error:
            raise ToolError(
                code="tool.upstream_error",
                message="Redis 只读查询失败",
            ) from error


class RedisTransport:
    """按目标目录创建最小权限 Redis 客户端。"""

    def __init__(
        self,
        *,
        hosts: Mapping[str, HostTarget],
        targets: Mapping[str, RedisTarget],
        limits: ToolLimits,
        secrets: EnvironmentSecretResolver,
        client_factory: RedisFactory = DEFAULT_REDIS_FACTORY,
    ) -> None:
        self._hosts = dict(hosts)
        self._targets = dict(targets)
        self._limits = limits
        self._secrets = secrets
        self._client_factory = client_factory

    def client(self, target: str) -> ReadOnlyRedisClient:
        configured = self._targets.get(target)
        if configured is None or configured.host not in self._hosts:
            raise ToolError(
                code="tool.configuration",
                message="Redis 目标未配置",
            )
        try:
            password = self._secrets.require(configured.password_env)
        except ConfigurationError as error:
            raise ToolError(
                code="tool.configuration",
                message="Redis 秘密配置缺失",
            ) from error
        try:
            client = self._client_factory(
                host=self._hosts[configured.host].address,
                port=configured.port,
                db=configured.database,
                username=configured.username,
                password=password,
                socket_connect_timeout=self._limits.connect_timeout_seconds,
                socket_timeout=self._limits.read_timeout_seconds,
                decode_responses=False,
            )
        except Exception as error:
            raise ToolError(
                code="tool.connection_failed",
                message="Redis 只读连接创建失败",
                retryable=True,
            ) from error
        return ReadOnlyRedisClient(client)
