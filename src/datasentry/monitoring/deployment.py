"""Prometheus/Grafana/Alertmanager 只读部署验收。"""

from typing import Any, Literal, Protocol

import httpx
from pydantic import Field

from datasentry.domain.common import DomainModel
from datasentry.monitoring.config import MonitoringEndpoints
from datasentry.redaction import redact_text

MonitoringCheckStatus = Literal["passed", "failed"]
DATASENTRY_ALERTMANAGER_ROUTE = "/api/alertmanager/webhook"


class HttpProbeResponse(DomainModel):
    """只读 HTTP 探测返回的安全子集。"""

    status_code: int
    text: str = ""
    json_body: Any | None = None

    @property
    def ok(self) -> bool:
        """HTTP status code 是否为 2xx。"""
        return 200 <= self.status_code < 300


class HttpProbeClient(Protocol):
    """部署验收使用的最小 HTTP GET 协议。"""

    def get(self, url: str) -> HttpProbeResponse:
        raise NotImplementedError  # pragma: no cover


class HttpxProbeClient:
    """基于 httpx 的真实只读 HTTP client。"""

    def __init__(self, *, timeout_seconds: float = 5.0) -> None:
        self._timeout_seconds = timeout_seconds

    def get(self, url: str) -> HttpProbeResponse:
        try:
            with httpx.Client(timeout=self._timeout_seconds, follow_redirects=False) as client:
                response = client.get(url)
        except httpx.RequestError as error:
            return HttpProbeResponse(
                status_code=0,
                text=redact_text(str(error)),
            )
        json_body: Any | None = None
        try:
            json_body = response.json()
        except ValueError:
            json_body = None
        return HttpProbeResponse(
            status_code=response.status_code,
            text=redact_text(response.text[:500]),
            json_body=json_body,
        )


class MonitoringCheckResult(DomainModel):
    """单项监控部署验收结果。"""

    name: str = Field(min_length=1)
    status: MonitoringCheckStatus
    summary: str = Field(min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)


class MonitoringDeploymentReport(DomainModel):
    """监控部署验收报告。"""

    status: MonitoringCheckStatus
    checks: list[MonitoringCheckResult]

    def check_by_name(self, name: str) -> MonitoringCheckResult:
        """按名称返回单项检查结果。"""
        for check in self.checks:
            if check.name == name:
                return check
        raise KeyError(name)


def run_monitoring_deployment_check(
    *,
    endpoints: MonitoringEndpoints,
    client: HttpProbeClient | None = None,
) -> MonitoringDeploymentReport:
    """执行 M8 监控栈只读部署验收。"""
    probe_client = client or HttpxProbeClient()
    checks = [
        _check_ready(
            client=probe_client,
            name="prometheus_ready",
            url=f"{endpoints.prometheus_base_url}/-/ready",
            passed_summary="Prometheus readiness 正常",
            failed_summary="Prometheus readiness 不可用",
        ),
        _check_prometheus_rules(endpoints=endpoints, client=probe_client),
        _check_ready(
            client=probe_client,
            name="alertmanager_ready",
            url=f"{endpoints.alertmanager_base_url}/-/ready",
            passed_summary="Alertmanager readiness 正常",
            failed_summary="Alertmanager readiness 不可用",
        ),
        _check_alertmanager_route(endpoints=endpoints, client=probe_client),
        _check_ready(
            client=probe_client,
            name="grafana_health",
            url=f"{endpoints.grafana_base_url}/api/health",
            passed_summary="Grafana health 正常",
            failed_summary="Grafana health 不可用",
        ),
    ]
    status: MonitoringCheckStatus = (
        "passed" if all(check.status == "passed" for check in checks) else "failed"
    )
    return MonitoringDeploymentReport(status=status, checks=checks)


def _check_ready(
    *,
    client: HttpProbeClient,
    name: str,
    url: str,
    passed_summary: str,
    failed_summary: str,
) -> MonitoringCheckResult:
    response = client.get(url)
    if response.ok:
        return MonitoringCheckResult(
            name=name,
            status="passed",
            summary=passed_summary,
            details={"status_code": response.status_code},
        )
    return MonitoringCheckResult(
        name=name,
        status="failed",
        summary=failed_summary,
        details={"status_code": response.status_code},
    )


def _check_prometheus_rules(
    *,
    endpoints: MonitoringEndpoints,
    client: HttpProbeClient,
) -> MonitoringCheckResult:
    response = client.get(f"{endpoints.prometheus_base_url}/api/v1/rules")
    alert_names = _extract_prometheus_alert_names(response.json_body)
    missing = [name for name in endpoints.expected_alerts if name not in alert_names]
    if response.ok and not missing:
        return MonitoringCheckResult(
            name="prometheus_rules_loaded",
            status="passed",
            summary="Prometheus 已加载关键 StreamLake 告警规则",
            details={"loaded_alerts": sorted(alert_names)},
        )
    return MonitoringCheckResult(
        name="prometheus_rules_loaded",
        status="failed",
        summary="Prometheus 缺少关键 StreamLake 告警规则",
        details={
            "status_code": response.status_code,
            "missing_alerts": missing,
            "loaded_alerts": sorted(alert_names),
        },
    )


def _check_alertmanager_route(
    *,
    endpoints: MonitoringEndpoints,
    client: HttpProbeClient,
) -> MonitoringCheckResult:
    response = client.get(f"{endpoints.alertmanager_base_url}/api/v2/status")
    original_config = _alertmanager_original_config(response.json_body)
    if response.ok and DATASENTRY_ALERTMANAGER_ROUTE in original_config:
        return MonitoringCheckResult(
            name="alertmanager_datasentry_route",
            status="passed",
            summary="Alertmanager 已配置 DataSentry Webhook 路由",
            details={"status_code": response.status_code},
        )
    return MonitoringCheckResult(
        name="alertmanager_datasentry_route",
        status="failed",
        summary="Alertmanager 未配置 DataSentry Webhook 路由",
        details={"status_code": response.status_code},
    )


def _extract_prometheus_alert_names(payload: Any) -> set[str]:
    if not isinstance(payload, dict) or payload.get("status") != "success":
        return set()
    data = payload.get("data")
    if not isinstance(data, dict):
        return set()
    names: set[str] = set()
    for group in data.get("groups", []):
        if not isinstance(group, dict):
            continue
        for rule in group.get("rules", []):
            if (
                isinstance(rule, dict)
                and rule.get("type") == "alerting"
                and isinstance(rule.get("name"), str)
            ):
                names.add(rule["name"])
    return names


def _alertmanager_original_config(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    config = payload.get("config")
    if not isinstance(config, dict):
        return ""
    original = config.get("original")
    return original if isinstance(original, str) else ""
