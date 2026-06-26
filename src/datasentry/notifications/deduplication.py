"""告警去重 key 生成。"""

from datasentry.notifications.alertmanager import AlertmanagerPayload

DEDUPLICATION_LABELS = (
    "alertname",
    "component",
    "service",
    "job",
    "instance",
    "severity",
)


def build_alert_deduplication_key(payload: AlertmanagerPayload) -> str:
    """基于稳定标签和 startsAt 生成告警去重 key。"""
    alert = payload.primary_alert
    labels = payload.common_labels | payload.group_labels | alert.labels
    parts = [f"{name}={labels.get(name, 'unknown')}" for name in DEDUPLICATION_LABELS]
    parts.append(f"startsAt={alert.starts_at}")
    return "|".join(parts)
