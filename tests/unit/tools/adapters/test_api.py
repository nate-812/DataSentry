import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import JsonValue

from datasentry.tools.adapters.api import ApiHealthTool

NOW = datetime(2026, 6, 25, 12, 0, tzinfo=UTC)
FIXTURES = Path(__file__).resolve().parents[3] / "fixtures/contracts/api"


class FixtureTransport:
    def __init__(self, *, spring_probe_filename: str = "spring_kline_latest.json") -> None:
        self._spring_probe_filename = spring_probe_filename
        self.requested_paths: list[tuple[str, str]] = []

    def get_json(self, target: str, path: str) -> JsonValue:
        self.requested_paths.append((target, path))
        if target == "spring_api" and path == "/actuator/health":
            filename = "spring_health.json"
        elif target == "spring_api":
            filename = self._spring_probe_filename
        else:
            filename = "ai_health_degraded.json"
        return json.loads((FIXTURES / filename).read_text(encoding="utf-8"))


def _fact(observations: list, metric: str):
    return next(item for item in observations if item.metric_or_fact == metric)


def test_spring_health_includes_process_and_read_probe() -> None:
    transport = FixtureTransport()
    observations = ApiHealthTool(transport, clock=lambda: NOW).execute(
        inspection_id="inspection-1",
        target="spring_api",
        arguments={"service": "spring_api"},
    )

    assert transport.requested_paths == [
        ("spring_api", "/actuator/health"),
        ("spring_api", "/api/kline/BTCUSDT?interval=1min&limit=1"),
    ]
    assert _fact(observations, "service_state").value == {"state": "RUNNING"}
    assert _fact(observations, "api_read_probe").value == {
        "status": "ok",
        "resource": "kline_latest",
    }


def test_spring_read_probe_accepts_empty_list_response() -> None:
    observations = ApiHealthTool(
        FixtureTransport(spring_probe_filename="spring_kline_latest_empty.json"),
        clock=lambda: NOW,
    ).execute(
        inspection_id="inspection-1",
        target="spring_api",
        arguments={"service": "spring_api"},
    )

    assert _fact(observations, "api_read_probe").value == {
        "status": "empty",
        "resource": "kline_latest",
    }


def test_ai_health_allows_milvus_degraded_mode() -> None:
    observations = ApiHealthTool(FixtureTransport(), clock=lambda: NOW).execute(
        inspection_id="inspection-1",
        target="ai_engine",
        arguments={"service": "ai_engine"},
    )

    assert _fact(observations, "service_state").value == {
        "state": "RUNNING",
        "mode": "degraded",
    }
    assert _fact(observations, "optional_dependency_state").value == {
        "dependency": "milvus",
        "state": "UNAVAILABLE_ALLOWED",
    }
