"""Alertmanager 到 DataSentry 的告警诊断闭环 smoke。"""

from typing import Any, Literal, Protocol

import httpx
from pydantic import Field

from datasentry.domain.common import DomainModel
from datasentry.monitoring.config import MonitoringEndpoints
from datasentry.redaction import redact_text

AlertSmokeStatus = Literal["passed", "failed"]
DEFAULT_ALERT_SMOKE_TIMEOUT_SECONDS = 60.0


class HttpSmokeResponse(DomainModel):
    """Alert smoke HTTP 响应的安全子集。"""

    status_code: int
    text: str = ""
    json_body: Any | None = None

    @property
    def ok(self) -> bool:
        """HTTP status code 是否为 2xx。"""
        return 200 <= self.status_code < 300


class HttpSmokeClient(Protocol):
    """Alert smoke 使用的最小 HTTP 协议。"""

    def get(self, url: str) -> HttpSmokeResponse:
        raise NotImplementedError  # pragma: no cover

    def post(self, url: str, json_body: object | None = None) -> HttpSmokeResponse:
        raise NotImplementedError  # pragma: no cover


class HttpxSmokeClient:
    """基于 httpx 的真实 DataSentry API smoke client。"""

    def __init__(self, *, timeout_seconds: float = DEFAULT_ALERT_SMOKE_TIMEOUT_SECONDS) -> None:
        self._timeout_seconds = timeout_seconds

    def get(self, url: str) -> HttpSmokeResponse:
        try:
            with httpx.Client(timeout=self._timeout_seconds, follow_redirects=False) as client:
                response = client.get(url)
        except httpx.RequestError as error:
            return HttpSmokeResponse(status_code=0, text=redact_text(str(error)))
        return _response_from_httpx(response)

    def post(self, url: str, json_body: object | None = None) -> HttpSmokeResponse:
        try:
            with httpx.Client(timeout=self._timeout_seconds, follow_redirects=False) as client:
                response = client.post(url, json=json_body)
        except httpx.RequestError as error:
            return HttpSmokeResponse(status_code=0, text=redact_text(str(error)))
        return _response_from_httpx(response)


class AlertSmokeStep(DomainModel):
    """Alert smoke 单步结果。"""

    name: str = Field(min_length=1)
    status: AlertSmokeStatus
    summary: str = Field(min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)


class AlertSmokeReport(DomainModel):
    """Alertmanager → DataSentry 诊断闭环 smoke 报告。"""

    status: AlertSmokeStatus
    incident_id: str | None = None
    diagnosis_question: str | None = None
    steps: list[AlertSmokeStep]


def run_alertmanager_smoke(
    *,
    endpoints: MonitoringEndpoints,
    payload: dict[str, object],
    client: HttpSmokeClient | None = None,
) -> AlertSmokeReport:
    """执行 Alertmanager Webhook 到 Incident/RCA/export 的闭环 smoke。"""
    smoke_client = client or HttpxSmokeClient()
    base_url = endpoints.datasentry_api_base_url
    webhook = smoke_client.post(f"{base_url}/api/alertmanager/webhook", json_body=payload)
    accepted_body = webhook.json_body if isinstance(webhook.json_body, dict) else {}
    incident_id = accepted_body.get("incident_id")
    diagnosis_question = accepted_body.get("diagnosis_question")
    steps = [
        _step(
            name="webhook_accepted",
            passed=(
                webhook.ok
                and accepted_body.get("accepted") is True
                and isinstance(incident_id, str)
                and bool(incident_id)
            ),
            passed_summary="DataSentry 已接收 Alertmanager Webhook 并创建 Incident",
            failed_summary="DataSentry Webhook 未完成 Incident 建档",
            response=webhook,
        )
    ]
    if steps[0].status == "failed":
        return AlertSmokeReport(
            status="failed",
            incident_id=None,
            diagnosis_question=None,
            steps=steps,
        )

    incident_id = str(incident_id)
    detail = smoke_client.get(f"{base_url}/api/incidents/{incident_id}")
    steps.append(
        _step(
            name="incident_detail_readable",
            passed=detail.ok and _incident_detail_matches(detail.json_body, incident_id),
            passed_summary="Incident detail 可读取",
            failed_summary="Incident detail 不可读取或 ID 不匹配",
            response=detail,
        )
    )
    timeline = smoke_client.get(f"{base_url}/api/incidents/{incident_id}/timeline")
    steps.append(
        _step(
            name="incident_timeline_readable",
            passed=timeline.ok and _timeline_has_alert_event(timeline.json_body),
            passed_summary="Incident timeline 包含告警事件",
            failed_summary="Incident timeline 缺少告警事件",
            response=timeline,
        )
    )
    rca = smoke_client.post(f"{base_url}/api/incidents/{incident_id}/rca")
    steps.append(
        _step(
            name="rca_generated",
            passed=rca.ok and _response_has_markdown(rca.json_body),
            passed_summary="RCA 草稿可生成",
            failed_summary="RCA 草稿生成失败",
            response=rca,
        )
    )
    exported = smoke_client.get(f"{base_url}/api/incidents/{incident_id}/export")
    steps.append(
        _step(
            name="markdown_export_readable",
            passed=exported.ok and bool(exported.text.strip()),
            passed_summary="Markdown export 可读取",
            failed_summary="Markdown export 不可读取",
            response=exported,
        )
    )
    status: AlertSmokeStatus = (
        "passed" if all(item.status == "passed" for item in steps) else "failed"
    )
    return AlertSmokeReport(
        status=status,
        incident_id=incident_id,
        diagnosis_question=(
            str(diagnosis_question) if isinstance(diagnosis_question, str) else None
        ),
        steps=steps,
    )


def _response_from_httpx(response: httpx.Response) -> HttpSmokeResponse:
    json_body: Any | None = None
    try:
        json_body = response.json()
    except ValueError:
        json_body = None
    return HttpSmokeResponse(
        status_code=response.status_code,
        text=redact_text(response.text[:500]),
        json_body=json_body,
    )


def _step(
    *,
    name: str,
    passed: bool,
    passed_summary: str,
    failed_summary: str,
    response: HttpSmokeResponse,
) -> AlertSmokeStep:
    return AlertSmokeStep(
        name=name,
        status="passed" if passed else "failed",
        summary=passed_summary if passed else failed_summary,
        details={
            "status_code": response.status_code,
            "response_excerpt": redact_text(response.text[:200]) if response.text else "",
        },
    )


def _incident_detail_matches(payload: Any, incident_id: str) -> bool:
    if not isinstance(payload, dict):
        return False
    incident = payload.get("incident")
    return isinstance(incident, dict) and incident.get("id") == incident_id


def _timeline_has_alert_event(payload: Any) -> bool:
    if not isinstance(payload, list):
        return False
    for item in payload:
        if not isinstance(item, dict):
            continue
        event_type = item.get("event_type")
        summary = item.get("summary")
        if event_type == "alert_fired":
            return True
        if isinstance(summary, str) and "Alertmanager" in summary:
            return True
    return False


def _response_has_markdown(payload: Any) -> bool:
    return isinstance(payload, dict) and isinstance(payload.get("markdown"), str)
