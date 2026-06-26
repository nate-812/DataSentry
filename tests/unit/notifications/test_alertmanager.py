import json
from pathlib import Path

import pytest

from datasentry.errors import DataSentryError
from datasentry.notifications import (
    AlertmanagerPayload,
    build_alert_deduplication_key,
    parse_alertmanager_payload,
)

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "alertmanager"


def test_parse_alertmanager_payload_extracts_group_and_alert() -> None:
    payload = json.loads((FIXTURE_DIR / "kline_freshness_firing.json").read_text())

    parsed = parse_alertmanager_payload(payload)

    assert isinstance(parsed, AlertmanagerPayload)
    assert parsed.status == "firing"
    assert parsed.group_labels["alertname"] == "KlineFreshnessStale"
    assert parsed.primary_alert.labels["component"] == "doris"
    assert parsed.primary_alert.starts_at == "2026-06-26T10:00:00Z"


def test_invalid_alertmanager_payload_raises_stable_error() -> None:
    payload = json.loads((FIXTURE_DIR / "invalid_payload.json").read_text())

    with pytest.raises(DataSentryError) as error:
        parse_alertmanager_payload(payload)

    assert error.value.code == "notification.invalid_payload"
    assert error.value.message == "Alertmanager Webhook 载荷无效"


def test_build_alert_deduplication_key_uses_stable_labels() -> None:
    payload = parse_alertmanager_payload(
        json.loads((FIXTURE_DIR / "kline_freshness_firing.json").read_text())
    )

    key = build_alert_deduplication_key(payload)

    assert key == (
        "alertname=KlineFreshnessStale|component=doris|service=streamlake|"
        "job=doris|instance=data1:9030|severity=critical|startsAt=2026-06-26T10:00:00Z"
    )
