import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import JsonValue

from datasentry.domain import ToolName
from datasentry.tools.adapters.flink import (
    FlinkBackpressureTool,
    FlinkCheckpointsTool,
    FlinkJobsTool,
    FlinkJobTool,
)

NOW = datetime(2026, 6, 25, 12, 0, tzinfo=UTC)
FIXTURES = Path(__file__).resolve().parents[3] / "fixtures/contracts/flink"


class FixtureHttpTransport:
    def __init__(self, *, backpressure_filename: str = "backpressure.json") -> None:
        self._backpressure_filename = backpressure_filename

    def get_json(self, target: str, path: str) -> JsonValue:
        del target
        if path == "/jobs/overview":
            filename = "jobs_overview.json"
        elif path.endswith("/checkpoints"):
            filename = "checkpoints.json"
        elif path.endswith("/backpressure"):
            filename = self._backpressure_filename
        else:
            filename = "job_details.json"
        return json.loads((FIXTURES / filename).read_text(encoding="utf-8"))


class DuplicateJobHttpTransport:
    def get_json(self, target: str, path: str) -> JsonValue:
        del target
        if path == "/jobs/overview":
            return {
                "jobs": [
                    {
                        "jid": "old-whale-job-id",
                        "name": "streamlake-whale-cep",
                        "state": "CANCELED",
                        "start-time": 1_772_302_000_000,
                    },
                    {
                        "jid": "new-whale-job-id",
                        "name": "streamlake-whale-cep",
                        "state": "RUNNING",
                        "start-time": 1_772_303_000_000,
                    },
                    {
                        "jid": "kline-job-id",
                        "name": "streamlake-kline-aggregation",
                        "state": "RUNNING",
                        "start-time": 1_772_301_000_000,
                    },
                ]
            }
        if path == "/jobs/new-whale-job-id":
            return {
                "jid": "new-whale-job-id",
                "name": "streamlake-whale-cep",
                "state": "RUNNING",
                "vertices": [],
            }
        raise AssertionError(f"unexpected path: {path}")


class DuplicateJobListHttpTransport:
    def get_json(self, target: str, path: str) -> JsonValue:
        del target
        if path == "/jobs/overview":
            return {
                "jobs": [
                    {
                        "jid": "new-whale-job-id",
                        "name": "streamlake-whale-cep",
                        "state": "RUNNING",
                        "start-time": 1_772_303_000_000,
                    },
                    {
                        "jid": "old-whale-job-id",
                        "name": "streamlake-whale-cep",
                        "state": "CANCELED",
                        "start-time": 1_772_302_000_000,
                    },
                    {
                        "jid": "kline-job-id",
                        "name": "streamlake-kline-aggregation",
                        "state": "RUNNING",
                        "start-time": 1_772_301_000_000,
                    },
                ]
            }
        raise AssertionError(f"unexpected path: {path}")


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


def test_get_flink_jobs_prefers_running_job_when_history_contains_same_name() -> None:
    observations = FlinkJobsTool(
        DuplicateJobListHttpTransport(),
        clock=lambda: NOW,
    ).execute(inspection_id="inspection-1", target="flink", arguments={})

    assert _fact(observations, "whale_job_state").value == {
        "job_id": "new-whale-job-id",
        "job_name": "streamlake-whale-cep",
        "state": "RUNNING",
    }


def test_get_flink_job_prefers_running_job_when_history_contains_same_name() -> None:
    observations = FlinkJobTool(DuplicateJobHttpTransport(), clock=lambda: NOW).execute(
        inspection_id="inspection-1",
        target="flink",
        arguments={"job": "whale"},
    )

    assert _fact(observations, "whale_job_details").value["job_id"] == "new-whale-job-id"


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


def test_get_flink_backpressure_accepts_camel_case_ok_level() -> None:
    observations = FlinkBackpressureTool(
        FixtureHttpTransport(backpressure_filename="backpressure_ok_camel.json"),
        clock=lambda: NOW,
    ).execute(
        inspection_id="inspection-1",
        target="flink",
        arguments={"job": "kline"},
    )

    assert _fact(observations, "backpressure_level").value == "ok"
    vertices = _fact(observations, "backpressure_vertices").value
    assert isinstance(vertices, list)
    assert vertices[0]["level"] == "ok"
