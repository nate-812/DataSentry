"""确定性 RCA Markdown 生成。"""

from datasentry.domain import Incident
from datasentry.incidents.models import IncidentRCAReport, IncidentTimelineEvent
from datasentry.tools.redaction import redact_text

BOUNDARY = "历史事件仅用于经验参考，当前状态必须以本次只读巡检证据为准。"


def _lines_or_empty(items: list[str], *, empty: str) -> list[str]:
    if not items:
        return [f"- {empty}"]
    return [f"- {redact_text(item)}" for item in items]


def build_rca_report(
    *,
    incident: Incident,
    timeline: list[IncidentTimelineEvent],
    evidence_summaries: list[str],
    similar_summaries: list[str],
    unknowns: list[str],
    next_version: int,
) -> IncidentRCAReport:
    """根据结构化事件材料生成 RCA Markdown 草稿。"""
    timeline_lines = [
        f"- {event.occurred_at.isoformat()} [{event.event_type.value}] {redact_text(event.summary)}"
        for event in timeline
    ]
    markdown = "\n".join(
        [
            f"# RCA：{redact_text(incident.title)}",
            "",
            f"> {BOUNDARY}",
            "",
            "## 事件摘要",
            "",
            f"- 状态：{incident.status.value}",
            f"- 严重级别：{incident.severity.value}",
            f"- 症状：{redact_text(incident.symptom)}",
            f"- 根因草稿：{redact_text(incident.root_cause or '未知')}",
            "",
            "## 时间线",
            "",
            *(timeline_lines or ["- 暂无时间线事件"]),
            "",
            "## 证据",
            "",
            *_lines_or_empty(evidence_summaries, empty="暂无证据摘要"),
            "",
            "## 历史相似事件",
            "",
            *_lines_or_empty(similar_summaries, empty="暂无相似历史事件"),
            "",
            "## 未知项",
            "",
            *_lines_or_empty(unknowns, empty="暂无未知项"),
            "",
        ]
    )
    return IncidentRCAReport(
        incident_id=incident.id,
        version=next_version,
        markdown=markdown,
        structured={
            "status": incident.status.value,
            "severity": incident.severity.value,
            "unknowns": [redact_text(unknown) for unknown in unknowns],
            "boundary": BOUNDARY,
        },
        generated_by="deterministic_template",
    )
