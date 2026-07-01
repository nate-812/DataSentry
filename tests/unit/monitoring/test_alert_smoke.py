from datasentry.monitoring import MonitoringEndpoints, run_alertmanager_smoke
from datasentry.monitoring.smoke import DEFAULT_ALERT_SMOKE_TIMEOUT_SECONDS, HttpSmokeResponse


class FakeSmokeClient:
    def __init__(self, responses: dict[tuple[str, str], HttpSmokeResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str]] = []

    def get(self, url: str) -> HttpSmokeResponse:
        self.calls.append(("GET", url))
        return self.responses[("GET", url)]

    def post(self, url: str, json_body: object | None = None) -> HttpSmokeResponse:
        del json_body
        self.calls.append(("POST", url))
        return self.responses[("POST", url)]


def _endpoints() -> MonitoringEndpoints:
    return MonitoringEndpoints(
        prometheus_base_url="http://prometheus.example:9090",
        grafana_base_url="http://grafana.example:3000",
        alertmanager_base_url="http://alertmanager.example:9093",
        datasentry_api_base_url="http://datasentry.example:8000",
        expected_alerts=["KlineFreshnessStale"],
    )


def _payload() -> dict[str, object]:
    return {
        "receiver": "datasentry-webhook",
        "status": "firing",
        "alerts": [{"labels": {"alertname": "KlineFreshnessStale"}}],
    }


def test_run_alertmanager_smoke_passes_complete_datasentry_loop() -> None:
    responses = {
        ("POST", "http://datasentry.example:8000/api/alertmanager/webhook"): HttpSmokeResponse(
            status_code=200,
            json_body={
                "accepted": True,
                "incident_id": "incident-1",
                "diagnosis_question": "为什么 K线数据不更新",
            },
        ),
        ("GET", "http://datasentry.example:8000/api/incidents/incident-1"): HttpSmokeResponse(
            status_code=200,
            json_body={"incident": {"id": "incident-1"}, "links": []},
        ),
        (
            "GET",
            "http://datasentry.example:8000/api/incidents/incident-1/timeline",
        ): HttpSmokeResponse(
            status_code=200,
            json_body=[{"event_type": "alert_fired", "summary": "Alertmanager firing"}],
        ),
        ("POST", "http://datasentry.example:8000/api/incidents/incident-1/rca"): HttpSmokeResponse(
            status_code=200,
            json_body={"markdown": "# RCA\n\n历史事件仅用于经验参考"},
        ),
        (
            "GET",
            "http://datasentry.example:8000/api/incidents/incident-1/export",
        ): HttpSmokeResponse(
            status_code=200,
            text="# RCA\n\n历史事件仅用于经验参考",
        ),
    }

    report = run_alertmanager_smoke(
        endpoints=_endpoints(),
        payload=_payload(),
        client=FakeSmokeClient(responses),
    )

    assert report.status == "passed"
    assert report.incident_id == "incident-1"
    assert report.diagnosis_question == "为什么 K线数据不更新"
    assert [step.name for step in report.steps] == [
        "webhook_accepted",
        "incident_detail_readable",
        "incident_timeline_readable",
        "rca_generated",
        "markdown_export_readable",
    ]
    assert all(step.status == "passed" for step in report.steps)


def test_alertmanager_smoke_fails_without_leaking_payload_on_webhook_error() -> None:
    responses = {
        ("POST", "http://datasentry.example:8000/api/alertmanager/webhook"): HttpSmokeResponse(
            status_code=500,
            text="token=secret-value",
        )
    }

    report = run_alertmanager_smoke(
        endpoints=_endpoints(),
        payload={"token": "secret-value"},
        client=FakeSmokeClient(responses),
    )

    assert report.status == "failed"
    assert report.incident_id is None
    assert report.steps[0].status == "failed"
    assert report.steps[0].details["status_code"] == 500
    assert "secret-value" not in report.model_dump_json()


def test_alertmanager_smoke_default_timeout_allows_live_diagnosis() -> None:
    assert DEFAULT_ALERT_SMOKE_TIMEOUT_SECONDS == 60.0
