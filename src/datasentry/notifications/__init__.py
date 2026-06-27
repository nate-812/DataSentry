"""告警通知解析、编排和格式化。"""

from datasentry.notifications.alertmanager import (
    AlertmanagerAlert,
    AlertmanagerPayload,
    parse_alertmanager_payload,
)
from datasentry.notifications.deduplication import build_alert_deduplication_key
from datasentry.notifications.messages import (
    NotificationContent,
    NotificationResult,
    build_generic_webhook_payload,
    build_wecom_markdown_payload,
)
from datasentry.notifications.service import (
    DiagnosisRunner,
    NotificationService,
    map_alert_to_question,
)

__all__ = [
    "AlertmanagerAlert",
    "AlertmanagerPayload",
    "DiagnosisRunner",
    "NotificationContent",
    "NotificationResult",
    "NotificationService",
    "build_alert_deduplication_key",
    "build_generic_webhook_payload",
    "build_wecom_markdown_payload",
    "map_alert_to_question",
    "parse_alertmanager_payload",
]
