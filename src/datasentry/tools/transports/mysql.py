"""仅执行代码目录中固定只读查询的 MySQL 协议传输。"""

from collections.abc import Callable, Mapping
from enum import StrEnum
from typing import Protocol, Self, cast

import pymysql
from pydantic import TypeAdapter, ValidationError
from pymysql.cursors import DictCursor
from pymysql.err import OperationalError as MySqlOperationalError
from pymysql.err import ProgrammingError as MySqlProgrammingError

from datasentry.errors import ConfigurationError
from datasentry.tools.errors import ToolError
from datasentry.tools.targets import (
    EnvironmentSecretResolver,
    HostTarget,
    MySqlTarget,
    ToolLimits,
)

ROW_ADAPTER = TypeAdapter(list[dict[str, object]])


class ReadOnlyQuery(StrEnum):
    DORIS_KLINE_FRESHNESS = (
        "SELECT MAX(open_time) AS latest_event_time, NOW() AS database_now FROM kline_1min"
    )
    DORIS_WHALE_FRESHNESS = (
        "SELECT MAX(alert_time) AS latest_event_time, NOW() AS database_now FROM whale_alert"
    )
    DORIS_RISK_FRESHNESS = (
        "SELECT MAX(trigger_time) AS latest_event_time, NOW() AS database_now FROM risk_trigger"
    )
    DORIS_AI_FRESHNESS = (
        "SELECT MAX(create_time) AS latest_event_time, NOW() AS database_now FROM ai_diagnosis"
    )
    MYSQL_WHALE_THRESHOLDS = (
        "SELECT symbol, threshold FROM whale_thresholds ORDER BY symbol LIMIT %s"
    )
    MYSQL_RISK_RULES = "SELECT symbol, threshold FROM risk_rules ORDER BY symbol LIMIT %s"


class CursorProtocol(Protocol):
    def execute(self, query: str, parameters: tuple[object, ...] = ()) -> object:
        raise NotImplementedError  # pragma: no cover

    def fetchall(self) -> object:
        raise NotImplementedError  # pragma: no cover

    def __enter__(self) -> Self:
        raise NotImplementedError  # pragma: no cover

    def __exit__(self, *args: object) -> None:
        raise NotImplementedError  # pragma: no cover


class ConnectionProtocol(Protocol):
    def cursor(self) -> CursorProtocol:
        raise NotImplementedError  # pragma: no cover

    def close(self) -> None:
        raise NotImplementedError  # pragma: no cover


ConnectionFactory = Callable[..., ConnectionProtocol]
DEFAULT_CONNECTION_FACTORY = cast(ConnectionFactory, pymysql.connect)


class MySqlTransport:
    """以只读 Session 执行固定查询目录。"""

    def __init__(
        self,
        *,
        hosts: Mapping[str, HostTarget],
        targets: Mapping[str, MySqlTarget],
        limits: ToolLimits,
        secrets: EnvironmentSecretResolver,
        connection_factory: ConnectionFactory = DEFAULT_CONNECTION_FACTORY,
    ) -> None:
        self._hosts = dict(hosts)
        self._targets = dict(targets)
        self._limits = limits
        self._secrets = secrets
        self._connection_factory = connection_factory

    @staticmethod
    def validate_query(query: str) -> None:
        """拒绝固定目录外误加入的写语句。"""
        normalized = query.lstrip().upper()
        if not normalized.startswith(("SELECT ", "SHOW ", "DESCRIBE ")):
            raise ToolError(
                code="tool.policy_denied",
                message="数据库工具拒绝非只读查询",
            )

    def fetch_all(
        self,
        target: str,
        query: ReadOnlyQuery,
        parameters: tuple[object, ...],
    ) -> list[dict[str, object]]:
        configured = self._targets.get(target)
        if configured is None or configured.host not in self._hosts:
            raise ToolError(
                code="tool.configuration",
                message="数据库目标未配置",
            )
        statement = query.value
        self.validate_query(statement)
        if configured.password_env is None:
            password = ""
        else:
            try:
                password = self._secrets.require(configured.password_env)
            except ConfigurationError as error:
                raise ToolError(
                    code="tool.configuration",
                    message="数据库秘密配置缺失",
                ) from error
        try:
            connection = self._connection_factory(
                host=self._hosts[configured.host].address,
                port=configured.port,
                user=configured.username,
                password=password,
                database=configured.database,
                connect_timeout=int(self._limits.connect_timeout_seconds),
                read_timeout=int(self._limits.read_timeout_seconds),
                write_timeout=int(self._limits.read_timeout_seconds),
                autocommit=False,
                cursorclass=DictCursor,
            )
        except MySqlOperationalError as error:
            code = error.args[0] if error.args else None
            if code in {1044, 1045}:
                raise ToolError(
                    code="tool.authentication_failed",
                    message="数据库认证或授权失败",
                ) from error
            if code == 1049:
                raise ToolError(
                    code="tool.configuration",
                    message="数据库名称不存在或不可访问",
                ) from error
            raise ToolError(
                code="tool.connection_failed",
                message="数据库只读连接失败",
                retryable=True,
            ) from error
        except Exception as error:
            raise ToolError(
                code="tool.connection_failed",
                message="数据库只读连接失败",
                retryable=True,
            ) from error
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET SESSION TRANSACTION READ ONLY")
                cursor.execute(statement, parameters)
                try:
                    return ROW_ADAPTER.validate_python(cursor.fetchall())
                except ValidationError as error:
                    raise ToolError(
                        code="tool.parse_failed",
                        message="数据库返回结构无效",
                    ) from error
        except ToolError:
            raise
        except (MySqlOperationalError, MySqlProgrammingError) as error:
            code = error.args[0] if error.args else None
            if code in {1054, 1146}:
                raise ToolError(
                    code="tool.configuration",
                    message="数据库表或字段不存在",
                ) from error
            raise ToolError(
                code="tool.upstream_error",
                message="数据库只读查询失败",
            ) from error
        except Exception as error:
            raise ToolError(
                code="tool.upstream_error",
                message="数据库只读查询失败",
            ) from error
        finally:
            connection.close()
