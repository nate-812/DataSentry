from datasentry.monitoring import MonitoringEndpoints, run_monitoring_deployment_check
from datasentry.monitoring.deployment import HttpProbeResponse


class FakeProbeClient:
    def __init__(self, responses: dict[str, HttpProbeResponse]) -> None:
        self.responses = responses
        self.paths: list[str] = []

    def get(self, url: str) -> HttpProbeResponse:
        self.paths.append(url)
        return self.responses[url]


def _endpoints() -> MonitoringEndpoints:
    return MonitoringEndpoints(
        prometheus_base_url="http://prometheus.example:9090",
        grafana_base_url="http://grafana.example:3000",
        alertmanager_base_url="http://alertmanager.example:9093",
        datasentry_api_base_url="http://datasentry.example:8000",
        expected_alerts=[
            "FlinkJobNotRunning",
            "KafkaConsumerLagHigh",
            "KlineFreshnessStale",
        ],
    )


def _successful_responses() -> dict[str, HttpProbeResponse]:
    return {
        "http://prometheus.example:9090/-/ready": HttpProbeResponse(
            status_code=200,
            text="Prometheus Server is Ready.",
        ),
        "http://prometheus.example:9090/api/v1/rules": HttpProbeResponse(
            status_code=200,
            json_body={
                "status": "success",
                "data": {
                    "groups": [
                        {
                            "rules": [
                                {"type": "alerting", "name": "FlinkJobNotRunning"},
                                {"type": "alerting", "name": "KafkaConsumerLagHigh"},
                                {"type": "alerting", "name": "KlineFreshnessStale"},
                            ]
                        }
                    ]
                },
            },
        ),
        "http://alertmanager.example:9093/-/ready": HttpProbeResponse(
            status_code=200,
            text="OK",
        ),
        "http://alertmanager.example:9093/api/v2/status": HttpProbeResponse(
            status_code=200,
            json_body={
                "config": {
                    "original": (
                        "receivers:\n"
                        "  - name: datasentry-webhook\n"
                        "    webhook_configs:\n"
                        "      - url: http://datasentry:8000/api/alertmanager/webhook\n"
                    )
                }
            },
        ),
        "http://grafana.example:3000/api/health": HttpProbeResponse(
            status_code=200,
            json_body={"database": "ok"},
        ),
    }


def test_run_monitoring_deployment_check_passes_when_stack_is_ready() -> None:
    client = FakeProbeClient(_successful_responses())

    report = run_monitoring_deployment_check(endpoints=_endpoints(), client=client)

    assert report.status == "passed"
    assert [item.name for item in report.checks] == [
        "prometheus_ready",
        "prometheus_rules_loaded",
        "alertmanager_ready",
        "alertmanager_datasentry_route",
        "grafana_health",
    ]
    assert all(item.status == "passed" for item in report.checks)


def test_deployment_check_fails_when_prometheus_rules_miss_expected_alert() -> None:
    responses = _successful_responses()
    responses["http://prometheus.example:9090/api/v1/rules"] = HttpProbeResponse(
        status_code=200,
        json_body={
            "status": "success",
            "data": {"groups": [{"rules": [{"type": "alerting", "name": "KafkaConsumerLagHigh"}]}]},
        },
    )

    report = run_monitoring_deployment_check(
        endpoints=_endpoints(),
        client=FakeProbeClient(responses),
    )

    rule_check = report.check_by_name("prometheus_rules_loaded")
    assert report.status == "failed"
    assert rule_check.status == "failed"
    assert rule_check.details["missing_alerts"] == [
        "FlinkJobNotRunning",
        "KlineFreshnessStale",
    ]


def test_deployment_check_fails_when_alertmanager_route_is_missing() -> None:
    responses = _successful_responses()
    responses["http://alertmanager.example:9093/api/v2/status"] = HttpProbeResponse(
        status_code=200,
        json_body={"config": {"original": "receivers: []\n"}},
    )

    report = run_monitoring_deployment_check(
        endpoints=_endpoints(),
        client=FakeProbeClient(responses),
    )

    route_check = report.check_by_name("alertmanager_datasentry_route")
    assert report.status == "failed"
    assert route_check.status == "failed"
    assert route_check.summary == "Alertmanager 未配置 DataSentry Webhook 路由"


def test_deployment_check_accepts_alertmanager_status_with_redacted_webhook_url() -> None:
    responses = _successful_responses()
    responses["http://alertmanager.example:9093/api/v2/status"] = HttpProbeResponse(
        status_code=200,
        json_body={
            "config": {
                "original": (
                    "route:\n"
                    "  receiver: datasentry-webhook\n"
                    "receivers:\n"
                    "- name: datasentry-webhook\n"
                    "  webhook_configs:\n"
                    "  - url: <secret>\n"
                )
            }
        },
    )

    report = run_monitoring_deployment_check(
        endpoints=_endpoints(),
        client=FakeProbeClient(responses),
    )

    route_check = report.check_by_name("alertmanager_datasentry_route")
    assert report.status == "passed"
    assert route_check.status == "passed"
