"""历史相似 Incident 排序。"""

from datasentry.domain import Incident, Severity
from datasentry.domain.common import DomainModel


class IncidentSearchCandidate(DomainModel):
    incident: Incident
    component: str
    failure_type: str
    stable_labels_hash: str
    root_cause: str | None = None


def rank_similar_incidents(
    candidates: list[IncidentSearchCandidate],
    *,
    component: str,
    failure_type: str,
    stable_labels_hash: str,
    root_cause_keywords: list[str],
    severity: Severity | None = None,
) -> list[IncidentSearchCandidate]:
    """按 fingerprint、组件、故障类型和根因关键词排序历史事件。"""

    def score(candidate: IncidentSearchCandidate) -> tuple[int, str]:
        value = 0
        if candidate.stable_labels_hash == stable_labels_hash:
            value += 100
        if candidate.component == component:
            value += 30
        if candidate.failure_type == failure_type:
            value += 30
        root_cause = (candidate.root_cause or "").casefold()
        if any(keyword.casefold() in root_cause for keyword in root_cause_keywords):
            value += 20
        if severity is not None and candidate.incident.severity is severity:
            value += 10
        return value, candidate.incident.updated_at.isoformat()

    return sorted(candidates, key=score, reverse=True)
