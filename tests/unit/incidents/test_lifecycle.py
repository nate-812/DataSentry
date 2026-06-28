from datasentry.domain import IncidentStatus
from datasentry.incidents import next_status_for_alert, next_status_for_diagnosis_failure


def test_new_firing_alert_moves_to_investigating() -> None:
    assert next_status_for_alert(None, alert_status="firing") is IncidentStatus.INVESTIGATING


def test_resolved_alert_moves_active_incident_to_verifying() -> None:
    assert (
        next_status_for_alert(IncidentStatus.INVESTIGATING, alert_status="resolved")
        is IncidentStatus.VERIFYING
    )


def test_diagnosis_failure_blocks_unresolved_incident() -> None:
    assert next_status_for_diagnosis_failure(IncidentStatus.INVESTIGATING) is IncidentStatus.BLOCKED
