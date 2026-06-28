"""Incident fingerprint 构建。"""

from datetime import datetime
from hashlib import sha256

from datasentry.domain import Severity
from datasentry.domain.common import utc_now
from datasentry.incidents.models import IncidentFingerprint

STABLE_LABELS = ("alertname", "component", "service", "job", "instance")


def stable_labels_hash(labels: dict[str, str]) -> str:
    """基于稳定告警标签生成顺序无关的 hash。"""
    parts = [f"{name}={labels.get(name, 'unknown')}" for name in STABLE_LABELS]
    return sha256("|".join(parts).encode("utf-8")).hexdigest()


def _severity(value: str | None) -> Severity:
    if value == Severity.CRITICAL.value:
        return Severity.CRITICAL
    if value == Severity.INFO.value:
        return Severity.INFO
    return Severity.WARNING


def build_alert_fingerprint(
    *,
    incident_id: str,
    labels: dict[str, str],
    observed_at: datetime | None = None,
) -> IncidentFingerprint:
    """从 Alertmanager labels 构建 Incident fingerprint。"""
    now = observed_at or utc_now()
    return IncidentFingerprint(
        incident_id=incident_id,
        component=labels.get("component") or labels.get("job") or "streamlake",
        failure_type=labels.get("alertname") or "streamlake_status",
        stable_labels_hash=stable_labels_hash(labels),
        severity=_severity(labels.get("severity")),
        first_seen_at=now,
        last_seen_at=now,
    )
