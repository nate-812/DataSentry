from datetime import UTC, datetime

import pytest
from pymysql.err import OperationalError as MySqlOperationalError
from pymysql.err import ProgrammingError as MySqlProgrammingError

from datasentry.tools.errors import ToolError
from datasentry.tools.targets import (
    EnvironmentSecretResolver,
    HostTarget,
    MySqlTarget,
    ToolLimits,
)
from datasentry.tools.transports.mysql import MySqlTransport, ReadOnlyQuery


class FakeCursor:
    description = (("value",),)

    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self.queries: list[str] = []
        self._rows = [{"value": 1}] if rows is None else rows

    def execute(self, query: str, parameters: tuple[object, ...] = ()) -> None:
        del parameters
        self.queries.append(query)

    def fetchall(self) -> list[dict[str, object]]:
        return self._rows

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *args: object) -> None:
        del args


class FakeConnection:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self.cursor_instance = FakeCursor(rows)

    def cursor(self) -> FakeCursor:
        return self.cursor_instance

    def close(self) -> None:
        return None


class QueryFailingCursor(FakeCursor):
    def execute(self, query: str, parameters: tuple[object, ...] = ()) -> None:
        super().execute(query, parameters)
        if query.startswith("SELECT"):
            raise MySqlProgrammingError(1146, "table does not exist")


class QueryFailingConnection(FakeConnection):
    def __init__(self) -> None:
        self.cursor_instance = QueryFailingCursor()


def test_mysql_transport_sets_read_only_before_fixed_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_MYSQL_PASSWORD", "secret")
    connection = FakeConnection()
    transport = MySqlTransport(
        hosts={"data1": HostTarget(address="192.0.2.10")},
        targets={
            "mysql": MySqlTarget(
                host="data1",
                port=3306,
                database="streamlake",
                username="readonly",
                password_env="TEST_MYSQL_PASSWORD",
            )
        },
        limits=ToolLimits(),
        secrets=EnvironmentSecretResolver(),
        connection_factory=lambda **_: connection,
    )

    rows = transport.fetch_all("mysql", ReadOnlyQuery.MYSQL_RISK_RULES, (20,))

    assert rows == [{"value": 1}]
    assert connection.cursor_instance.queries[0] == "SET SESSION TRANSACTION READ ONLY"
    assert connection.cursor_instance.queries[1].startswith("SELECT")


def test_mysql_transport_uses_empty_password_when_target_is_passwordless(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TEST_MYSQL_PASSWORD", raising=False)
    connection = FakeConnection()
    captured_password: str | None = None

    def connection_factory(**kwargs: object) -> FakeConnection:
        nonlocal captured_password
        captured_password = str(kwargs["password"])
        return connection

    transport = MySqlTransport(
        hosts={"data1": HostTarget(address="192.0.2.10")},
        targets={
            "doris": MySqlTarget(
                host="data1",
                port=9030,
                database="default",
                username="root",
            )
        },
        limits=ToolLimits(),
        secrets=EnvironmentSecretResolver(),
        connection_factory=connection_factory,
    )

    rows = transport.fetch_all("doris", ReadOnlyQuery.DORIS_KLINE_FRESHNESS, ())

    assert rows == [{"value": 1}]
    assert captured_password == ""


def test_mysql_transport_preserves_datetime_values_for_adapters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_MYSQL_PASSWORD", "secret")
    latest = datetime(2026, 6, 26, 17, 6, tzinfo=UTC)
    connection = FakeConnection(
        [{"latest_event_time": latest, "database_now": None}],
    )
    transport = MySqlTransport(
        hosts={"data1": HostTarget(address="192.0.2.10")},
        targets={
            "doris": MySqlTarget(
                host="data1",
                port=9030,
                database="streamlake",
                username="root",
                password_env="TEST_MYSQL_PASSWORD",
            )
        },
        limits=ToolLimits(),
        secrets=EnvironmentSecretResolver(),
        connection_factory=lambda **_: connection,
    )

    rows = transport.fetch_all("doris", ReadOnlyQuery.DORIS_KLINE_FRESHNESS, ())

    assert rows == [{"latest_event_time": latest, "database_now": None}]


def test_mysql_transport_reports_missing_secret_as_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TEST_MYSQL_PASSWORD", raising=False)
    called = False

    def connection_factory(**_: object) -> FakeConnection:
        nonlocal called
        called = True
        return FakeConnection()

    transport = MySqlTransport(
        hosts={"data1": HostTarget(address="192.0.2.10")},
        targets={
            "mysql": MySqlTarget(
                host="data1",
                port=3306,
                database="streamlake",
                username="readonly",
                password_env="TEST_MYSQL_PASSWORD",
            )
        },
        limits=ToolLimits(),
        secrets=EnvironmentSecretResolver(),
        connection_factory=connection_factory,
    )

    with pytest.raises(ToolError) as raised:
        transport.fetch_all("mysql", ReadOnlyQuery.MYSQL_RISK_RULES, (20,))

    assert raised.value.code == "tool.configuration"
    assert called is False


def test_mysql_transport_reports_access_denied_as_authentication_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_MYSQL_PASSWORD", "secret")

    def connection_factory(**_: object) -> FakeConnection:
        raise MySqlOperationalError(1045, "access denied")

    transport = MySqlTransport(
        hosts={"data1": HostTarget(address="192.0.2.10")},
        targets={
            "mysql": MySqlTarget(
                host="data1",
                port=3306,
                database="streamlake",
                username="readonly",
                password_env="TEST_MYSQL_PASSWORD",
            )
        },
        limits=ToolLimits(),
        secrets=EnvironmentSecretResolver(),
        connection_factory=connection_factory,
    )

    with pytest.raises(ToolError) as raised:
        transport.fetch_all("mysql", ReadOnlyQuery.MYSQL_RISK_RULES, (20,))

    assert raised.value.code == "tool.authentication_failed"


def test_mysql_transport_reports_unknown_database_as_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_MYSQL_PASSWORD", "secret")

    def connection_factory(**_: object) -> FakeConnection:
        raise MySqlOperationalError(1049, "unknown database")

    transport = MySqlTransport(
        hosts={"data1": HostTarget(address="192.0.2.10")},
        targets={
            "mysql": MySqlTarget(
                host="data1",
                port=3306,
                database="missing",
                username="readonly",
                password_env="TEST_MYSQL_PASSWORD",
            )
        },
        limits=ToolLimits(),
        secrets=EnvironmentSecretResolver(),
        connection_factory=connection_factory,
    )

    with pytest.raises(ToolError) as raised:
        transport.fetch_all("mysql", ReadOnlyQuery.MYSQL_RISK_RULES, (20,))

    assert raised.value.code == "tool.configuration"


def test_mysql_transport_reports_missing_table_as_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_MYSQL_PASSWORD", "secret")
    transport = MySqlTransport(
        hosts={"data1": HostTarget(address="192.0.2.10")},
        targets={
            "mysql": MySqlTarget(
                host="data1",
                port=3306,
                database="risk_control",
                username="readonly",
                password_env="TEST_MYSQL_PASSWORD",
            )
        },
        limits=ToolLimits(),
        secrets=EnvironmentSecretResolver(),
        connection_factory=lambda **_: QueryFailingConnection(),
    )

    with pytest.raises(ToolError) as raised:
        transport.fetch_all("mysql", ReadOnlyQuery.MYSQL_RISK_RULES, (20,))

    assert raised.value.code == "tool.configuration"


def test_read_only_query_catalog_rejects_non_read_statement() -> None:
    with pytest.raises(ToolError):
        MySqlTransport.validate_query("DELETE FROM risk_rules")


def test_doris_freshness_queries_compare_against_session_now() -> None:
    queries = {
        ReadOnlyQuery.DORIS_KLINE_FRESHNESS: "MAX(open_time)",
        ReadOnlyQuery.DORIS_WHALE_FRESHNESS: "MAX(alert_time)",
        ReadOnlyQuery.DORIS_RISK_FRESHNESS: "MAX(trigger_time)",
        ReadOnlyQuery.DORIS_AI_FRESHNESS: "MAX(create_time)",
    }

    for query, expected_column in queries.items():
        assert expected_column in query.value
        assert "NOW() AS database_now" in query.value
        assert "UTC_TIMESTAMP()" not in query.value


def test_mysql_rule_sample_queries_alias_live_columns_to_threshold() -> None:
    assert "max_single_qty AS threshold" in ReadOnlyQuery.MYSQL_RISK_RULES.value
    assert "threshold_quote AS threshold" in ReadOnlyQuery.MYSQL_WHALE_THRESHOLDS.value
