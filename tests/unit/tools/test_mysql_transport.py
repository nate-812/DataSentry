import pytest

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

    def __init__(self) -> None:
        self.queries: list[str] = []

    def execute(self, query: str, parameters: tuple[object, ...] = ()) -> None:
        del parameters
        self.queries.append(query)

    def fetchall(self) -> list[dict[str, object]]:
        return [{"value": 1}]

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *args: object) -> None:
        del args


class FakeConnection:
    def __init__(self) -> None:
        self.cursor_instance = FakeCursor()

    def cursor(self) -> FakeCursor:
        return self.cursor_instance

    def close(self) -> None:
        return None


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


def test_read_only_query_catalog_rejects_non_read_statement() -> None:
    with pytest.raises(ToolError):
        MySqlTransport.validate_query("DELETE FROM risk_rules")
