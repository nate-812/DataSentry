from datetime import UTC, datetime
from decimal import Decimal

from datasentry.tools.adapters.mysql import MySqlTableSampleTool
from datasentry.tools.transports.mysql import ReadOnlyQuery

NOW = datetime(2026, 6, 25, 12, 0, tzinfo=UTC)


class FixtureTransport:
    def fetch_all(
        self,
        target: str,
        query: ReadOnlyQuery,
        parameters: tuple[object, ...],
    ) -> list[dict[str, object]]:
        del target, query
        assert parameters == (20,)
        return [{"symbol": "BTCUSDT", "threshold": "1000000"}]


def test_mysql_sample_is_bounded_and_structured() -> None:
    observations = MySqlTableSampleTool(
        FixtureTransport(),
        clock=lambda: NOW,
    ).execute(
        inspection_id="inspection-1",
        target="mysql",
        arguments={"table": "risk_rules", "limit": 20},
    )

    assert observations[0].metric_or_fact == "mysql_table_sample"
    assert observations[0].value == {
        "table": "risk_rules",
        "rows": [{"symbol": "BTCUSDT", "threshold": "1000000"}],
        "limit": 20,
    }


class DecimalTransport:
    def fetch_all(
        self,
        target: str,
        query: ReadOnlyQuery,
        parameters: tuple[object, ...],
    ) -> list[dict[str, object]]:
        del target, query, parameters
        return [{"symbol": "BTCUSDT", "threshold": Decimal("100.00000000")}]


def test_mysql_sample_converts_decimal_values_to_json() -> None:
    observations = MySqlTableSampleTool(
        DecimalTransport(),
        clock=lambda: NOW,
    ).execute(
        inspection_id="inspection-1",
        target="mysql",
        arguments={"table": "risk_rules", "limit": 20},
    )

    assert observations[0].value == {
        "table": "risk_rules",
        "rows": [{"symbol": "BTCUSDT", "threshold": "100.00000000"}],
        "limit": 20,
    }
