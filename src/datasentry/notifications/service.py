"""告警到诊断通知的编排。"""

from typing import Protocol

from datasentry.domain import Finding
from datasentry.notifications.alertmanager import AlertmanagerPayload
from datasentry.notifications.deduplication import build_alert_deduplication_key
from datasentry.notifications.messages import (
    NotificationContent,
    NotificationResult,
    build_generic_webhook_payload,
    build_wecom_markdown_payload,
)
from datasentry.tools import LiveInspectionResult
from datasentry.tools.redaction import redact_text


class DiagnosisRunner(Protocol):
    """执行现场只读巡检并返回诊断结果的最小协议。"""

    def run(self, question: str) -> LiveInspectionResult:
        """执行指定诊断问题。"""
        raise NotImplementedError  # pragma: no cover


ALERT_QUESTIONS = {
    "FlinkJobNotRunning": "为什么 Flink 关键 Job 未运行",
    "KlineFreshnessStale": "为什么 K线数据不更新",
    "KafkaConsumerLagHigh": "为什么 Kafka 消费延迟升高",
}


def map_alert_to_question(payload: AlertmanagerPayload) -> str:
    """将告警名称映射为 DataSentry 诊断问题。"""
    alertname = (
        payload.primary_alert.labels.get("alertname")
        or payload.common_labels.get("alertname")
        or payload.group_labels.get("alertname")
        or ""
    )
    return ALERT_QUESTIONS.get(alertname, "请巡检 StreamLake 当前状态")


class NotificationService:
    """构建告警诊断通知，不负责真实网络发送。"""

    def __init__(self, *, diagnosis_runner: DiagnosisRunner) -> None:
        self._diagnosis_runner = diagnosis_runner

    def build(self, payload: AlertmanagerPayload) -> NotificationResult:
        """执行诊断并构建企业微信和通用 Webhook 消息。"""
        question = map_alert_to_question(payload)
        labels = payload.common_labels | payload.group_labels | payload.primary_alert.labels
        unknowns: list[str] = []
        findings: list[Finding] = []
        try:
            result = self._diagnosis_runner.run(question)
            findings = result.diagnosis.aggregate.findings
            for finding in findings:
                unknowns.extend(redact_text(unknown) for unknown in finding.unknowns)
        except Exception as error:
            unknowns.append(f"诊断执行失败：{redact_text(str(error))}")
        content = NotificationContent(
            status=payload.status,
            severity=labels.get("severity", "unknown"),
            component=labels.get("component", "streamlake"),
            deduplication_key=build_alert_deduplication_key(payload),
            diagnosis_question=question,
            findings=findings,
            unknowns=list(dict.fromkeys(unknowns)),
        )
        return NotificationResult(
            content=content,
            wecom_markdown=build_wecom_markdown_payload(content),
            generic_webhook=build_generic_webhook_payload(content),
        )
