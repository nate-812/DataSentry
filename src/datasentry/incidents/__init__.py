"""事件记忆领域模型和纯函数导出。"""

from datasentry.incidents.fingerprints import build_alert_fingerprint, stable_labels_hash
from datasentry.incidents.lifecycle import next_status_for_alert, next_status_for_diagnosis_failure
from datasentry.incidents.models import (
    IncidentAction,
    IncidentDetail,
    IncidentFingerprint,
    IncidentLink,
    IncidentLinkKind,
    IncidentRCAReport,
    IncidentTimelineEvent,
    IncidentTimelineEventType,
    IncidentUpsertResult,
)
from datasentry.incidents.search import IncidentSearchCandidate, rank_similar_incidents

__all__ = [
    "IncidentAction",
    "IncidentDetail",
    "IncidentFingerprint",
    "IncidentLink",
    "IncidentLinkKind",
    "IncidentRCAReport",
    "IncidentSearchCandidate",
    "IncidentService",
    "IncidentTimelineEvent",
    "IncidentTimelineEventType",
    "IncidentUpsertResult",
    "build_alert_fingerprint",
    "build_rca_report",
    "next_status_for_alert",
    "next_status_for_diagnosis_failure",
    "rank_similar_incidents",
    "stable_labels_hash",
]


def __getattr__(name: str) -> object:
    if name == "IncidentService":
        from datasentry.incidents.service import IncidentService

        return IncidentService
    if name == "build_rca_report":
        from datasentry.incidents.rca import build_rca_report

        return build_rca_report
    raise AttributeError(name)
