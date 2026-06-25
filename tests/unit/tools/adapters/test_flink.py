import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import JsonValue

from datasentry.domain import ToolName
from datasentry.tools.adapters.flink import (
    FlinkBackpressureTool,
    FlinkCheckpointsTool,
    FlinkJobsTool,
)

NOW = datetime(2026, 6, 25, 12, 0, tzinfo=UTC)
FIXTURES = Path(__file__).resolve().parents[3] / "fixtures/contracts/flink"


class FixtureHttpTransport:
    def get_json(self, target: str, path: str) -> JsonValue:
        del target
        if path == "/jobs/overview":
            filename = "jobs_overview.json"
        elif path.endswith("/checkpoints"):
            filename = "checkpoints.json"
        elif path.endswith("/backpressure"):
            filename = "backpressure.json"
        else:
            filename = "job_details.json"
        return json.loads((FIXTURES / filename).read_text(encoding="utf-8"))


def _fact(observations: list, metric: str):
    return next(item for item in observations if item.metric_or_fact == metric)


def test_get_flink_jobs_maps_known_jobs_and_missing_job() -> None:
    tool = FlinkJobsTool(FixtureHttpTransport(), clock=lambda: NOW)

    observations = tool.execute(
        inspection_id="inspection-1",
        target="flink",
        arguments={},
    )

    assert tool.name is ToolName.GET_FLINK_JOBS
    assert _fact(observations, "kline_job_state").value == {
        "job_id": "kline-job-id",
        "job_name": "streamlake-kline-aggregation",
        "state": "RUNNING",
    }
    assert _fact(observations, "risk_job_state").value == {
        "job_id": None,
        "job_name": "streamlake-risk-control",
        "state": "MISSING",
    }


def test_get_flink_checkpoints_maps_m1_failure_fact() -> None:
    observations = FlinkCheckpointsTool(
        FixtureHttpTransport(),
        clock=lambda: NOW,
    ).execute(
        inspection_id="inspection-1",
        target="flink",
        arguments={"job": "kline"},
    )

    assert _fact(observations, "checkpoint_consecutive_failures").value == 0
    assert _fact(observations, "checkpoint_latest_duration_ms").value == 1500
    assert _fact(observations, "checkpoint_latest_size_bytes").value == 4096


def test_get_flink_backpressure_returns_level_and_limited_vertices() -> None:
    observations = FlinkBackpressureTool(
        FixtureHttpTransport(),
        clock=lambda: NOW,
    ).execute(
        inspection_id="inspection-1",
        target="flink",
        arguments={"job": "kline"},
    )

    assert _fact(observations, "backpressure_level").value == "high"
    vertices = _fact(observations, "backpressure_vertices").value
    assert isinstance(vertices, list)
    assert len(vertices) == 2
