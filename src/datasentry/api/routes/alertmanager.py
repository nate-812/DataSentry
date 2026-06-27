"""Alertmanager Webhook API。"""

from typing import Any

from fastapi import APIRouter

from datasentry.notifications import parse_alertmanager_payload

router = APIRouter(tags=["alertmanager"])


@router.post("/alertmanager/webhook")
def receive_alertmanager_webhook(payload: dict[str, Any]) -> dict[str, object]:
    parsed = parse_alertmanager_payload(payload)
    return {
        "status": "accepted",
        "alert_count": len(parsed.alerts),
        "group_key": parsed.group_key,
    }
