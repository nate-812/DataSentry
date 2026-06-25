from datetime import UTC, datetime, timedelta

from datasentry.tools.adapters.doris import DorisFreshnessTool
from datasentry.tools.transports.mysql import ReadOnlyQuery

NOW = datetime(2026, 6, 25, 12, 0, tzinfo=UTC)


class FixtureMySqlTransport:
    def fetch_all(
        self,
        target: str,
        query: ReadOnlyQuery,
        parameters: tuple[object, ...],
    ) -> list[dict[str, object]]:
        del target, query, parameters
        return [
            {
                "latest_event_time": NOW - timedelta(minutes=15),
                "database_now": NOW,
            }
        ]


def _fact(observations: list, metric: str):
    return next(item for item in observations if item.metric_or_fact == metric)


def test_doris_freshness_maps_kline_m1_fact() -> None:
    observations = DorisFreshnessTool(
        FixtureMySqlTransport(),
        clock=lambda: NOW,
    ).execute(
        inspection_id="inspection-1",
        target="doris",
        arguments={"table": "kline_1min"},
    )

    assert _fact(observations, "kline_freshness_seconds").value == 900
    assert (
        _fact(observations, "kline_latest_event_time").value
        == (NOW - timedelta(minutes=15)).isoformat()
    )
