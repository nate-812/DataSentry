from datetime import UTC, datetime

from datasentry.domain import Incident, Severity
from datasentry.incidents import IncidentSearchCandidate, rank_similar_incidents

NOW = datetime(2026, 6, 28, 10, 0, tzinfo=UTC)


def test_rank_similar_incidents_prefers_exact_component_and_failure_type() -> None:
    exact = IncidentSearchCandidate(
        incident=Incident(
            id="incident-1",
            title="K线延迟",
            symptom="K线不更新",
            severity=Severity.WARNING,
            opened_at=NOW,
            updated_at=NOW,
        ),
        component="flink",
        failure_type="KlineFreshnessStale",
        stable_labels_hash="hash-1",
        root_cause="Flink Job lag",
    )
    component_only = exact.model_copy(
        update={
            "incident": exact.incident.model_copy(update={"id": "incident-2"}),
            "failure_type": "KafkaConsumerLagHigh",
        }
    )

    ranked = rank_similar_incidents(
        [component_only, exact],
        component="flink",
        failure_type="KlineFreshnessStale",
        stable_labels_hash="hash-1",
        root_cause_keywords=["Flink"],
    )

    assert [candidate.incident.id for candidate in ranked] == ["incident-1", "incident-2"]
