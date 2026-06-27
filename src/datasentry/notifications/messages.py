"""告警通知消息格式化。"""

from typing import cast

from pydantic import BaseModel, ConfigDict, JsonValue

from datasentry.domain import EvidenceStatus, Finding
from datasentry.tools.redaction import redact_text, redact_value


class NotificationContent(BaseModel):
    """格式化通知所需的稳定内容。"""

    model_config = ConfigDict(frozen=True)

    status: str
    severity: str
    component: str
    deduplication_key: str
    diagnosis_question: str
    findings: list[Finding]
    unknowns: list[str]


class NotificationResult(BaseModel):
    """一次通知构建的双格式输出。"""

    model_config = ConfigDict(frozen=True)

    content: NotificationContent
    wecom_markdown: dict[str, object]
    generic_webhook: dict[str, object]


def _finding_summaries(findings: list[Finding]) -> list[str]:
    return [finding.claim for finding in findings]


def _confirmed_evidence(findings: list[Finding]) -> list[dict[str, object]]:
    evidence_items: list[dict[str, object]] = []
    for finding in findings:
        for evidence in finding.evidence:
            if evidence.status == EvidenceStatus.CONFIRMED:
                evidence_items.append(
                    {
                        "claim": evidence.claim,
                        "source": evidence.source,
                        "target": evidence.target,
                        "observed_at": evidence.observed_at.isoformat(),
                        "summary": evidence.summary,
                    }
                )
    return evidence_items


def _recommended_actions(findings: list[Finding]) -> list[str]:
    return list(dict.fromkeys(finding.recommendation for finding in findings))


def build_generic_webhook_payload(content: NotificationContent) -> dict[str, object]:
    """生成通用 Webhook JSON 载荷。"""
    payload = {
        "status": content.status,
        "severity": content.severity,
        "component": content.component,
        "deduplication_key": content.deduplication_key,
        "diagnosis_question": content.diagnosis_question,
        "diagnosis_status": "confirmed" if content.findings else "unknown",
        "finding_summaries": _finding_summaries(content.findings),
        "confirmed_evidence": _confirmed_evidence(content.findings),
        "unknowns": content.unknowns,
        "recommended_actions": _recommended_actions(content.findings),
    }
    return cast(dict[str, object], redact_value(cast(JsonValue, payload)))


def build_wecom_markdown_payload(content: NotificationContent) -> dict[str, object]:
    """生成企业微信机器人 Markdown 载荷。"""
    generic = build_generic_webhook_payload(content)
    lines = [
        f"### DataSentry 告警诊断：{generic['severity']}",
        f"- 状态：{generic['status']}",
        f"- 组件：{generic['component']}",
        f"- 问题：{generic['diagnosis_question']}",
        f"- 去重：{generic['deduplication_key']}",
        "",
        "**当前结论**",
    ]
    findings = cast(list[str], generic["finding_summaries"])
    if findings:
        lines.extend(f"- {item}" for item in findings)
    else:
        lines.append("- 当前诊断结论未知")
    lines.append("")
    lines.append("**已确认关键证据**")
    evidence_items = cast(list[dict[str, object]], generic["confirmed_evidence"])
    if evidence_items:
        for evidence in evidence_items:
            lines.append(
                "- "
                f"{evidence['claim']}，来源={evidence['source']}，"
                f"时间={evidence['observed_at']}，摘要={evidence['summary']}"
            )
    else:
        lines.append("- 暂无已确认实时证据")
    lines.append("")
    lines.append("**未知项**")
    unknowns = cast(list[str], generic["unknowns"])
    if unknowns:
        lines.extend(f"- {item}" for item in unknowns)
    else:
        lines.append("- 无")
    lines.append("")
    lines.append("**建议动作**")
    actions = cast(list[str], generic["recommended_actions"])
    if actions:
        lines.extend(f"- {item}" for item in actions)
    else:
        lines.append("- 人工查看告警上下文并补充只读巡检")
    return {"msgtype": "markdown", "markdown": {"content": redact_text("\n".join(lines))}}
