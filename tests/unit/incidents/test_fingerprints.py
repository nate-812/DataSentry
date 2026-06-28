from datasentry.domain import Severity
from datasentry.incidents import build_alert_fingerprint, stable_labels_hash


def test_stable_labels_hash_ignores_unstable_annotations() -> None:
    labels = {
        "alertname": "KlineFreshnessStale",
        "component": "flink",
        "instance": "data1:8081",
        "description": "changes often",
    }

    assert stable_labels_hash(labels) == stable_labels_hash(dict(reversed(labels.items())))


def test_build_alert_fingerprint_uses_component_and_alertname() -> None:
    fingerprint = build_alert_fingerprint(
        incident_id="incident-1",
        labels={
            "alertname": "KlineFreshnessStale",
            "component": "flink",
            "severity": "warning",
        },
    )

    assert fingerprint.component == "flink"
    assert fingerprint.failure_type == "KlineFreshnessStale"
    assert fingerprint.severity is Severity.WARNING
