"""Incident 生命周期纯函数。"""

from datasentry.domain import IncidentStatus


def next_status_for_alert(
    current: IncidentStatus | None,
    *,
    alert_status: str,
) -> IncidentStatus:
    """根据 Alertmanager 状态计算下一步 Incident 状态。"""
    if alert_status == "resolved":
        if current is IncidentStatus.RESOLVED:
            return IncidentStatus.RESOLVED
        return IncidentStatus.VERIFYING
    if current in {IncidentStatus.BLOCKED, IncidentStatus.ESCALATED}:
        return current
    return IncidentStatus.INVESTIGATING


def next_status_for_diagnosis_failure(current: IncidentStatus) -> IncidentStatus:
    """诊断失败时进入 blocked，但不重新打开已解决事件。"""
    if current is IncidentStatus.RESOLVED:
        return IncidentStatus.RESOLVED
    return IncidentStatus.BLOCKED
