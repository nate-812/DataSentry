"""Alertmanager Webhook API。"""

from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder

from datasentry.api.dependencies import get_incident_service
from datasentry.incidents.service import IncidentService
from datasentry.notifications import parse_alertmanager_payload

router = APIRouter(tags=["alertmanager"])


@router.post("/alertmanager/webhook")
def receive_alertmanager_webhook(
    payload: dict[str, Any],
    incident_service: Annotated[IncidentService, Depends(get_incident_service)],
) -> dict[str, object]:
    parsed = parse_alertmanager_payload(payload)
    result = incident_service.handle_alertmanager_payload(parsed)
    return cast(dict[str, object], jsonable_encoder(result))
