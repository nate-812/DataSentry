import json
from datetime import UTC, datetime
from typing import cast

from datasentry.domain import Evidence, EvidenceStatus, Finding, Severity
from datasentry.notifications.messages import (
    NotificationContent,
    build_generic_webhook_payload,
    build_wecom_markdown_payload,
)

NOW = datetime(2026, 6, 26, 10, 5, tzinfo=UTC)


def _content() -> NotificationContent:
    evidence = Evidence(
        claim="Doris kline_1min 最新业务时间超出阈值",
        status=EvidenceStatus.CONFIRMED,
        source="doris_sql",
        target="data1:9030",
        observed_at=NOW,
        summary="latest_event_time=2026-06-26T09:50:00Z",
    )
    finding = Finding(
        inspection_id="inspection-1",
        severity=Severity.CRITICAL,
        status=EvidenceStatus.CONFIRMED,
        claim="K线链路数据新鲜度异常",
        evidence=[evidence],
        impact="前端可能显示过期 K 线",
        recommendation="检查 Flink Kline Job 和 Doris 写入延迟",
        unknowns=["尚未确认 Spring API 缓存状态"],
        created_at=NOW,
    )
    return NotificationContent(
        status="firing",
        severity="critical",
        component="doris",
        deduplication_key="alertname=KlineFreshnessStale|component=doris",
        diagnosis_question="为什么 K线数据不更新",
        findings=[finding],
        unknowns=["尚未确认 Spring API 缓存状态"],
    )


def test_build_wecom_markdown_payload_contains_evidence_and_redacts_secret() -> None:
    content = _content().model_copy(
        update={
            "deduplication_key": "alertname=KlineFreshnessStale|token=secret-value",
        }
    )

    payload = build_wecom_markdown_payload(content)

    assert payload["msgtype"] == "markdown"
    markdown_payload = cast(dict[str, str], payload["markdown"])
    markdown = markdown_payload["content"]
    assert "K线链路数据新鲜度异常" in markdown
    assert "doris_sql" in markdown
    assert "secret-value" not in markdown
    assert "[REDACTED]" in markdown


def test_build_generic_webhook_payload_is_stable_json_shape() -> None:
    payload = build_generic_webhook_payload(_content())

    json.dumps(payload, ensure_ascii=False)
    assert payload["status"] == "firing"
    assert payload["severity"] == "critical"
    assert payload["component"] == "doris"
    assert payload["diagnosis_question"] == "为什么 K线数据不更新"
    assert payload["finding_summaries"] == ["K线链路数据新鲜度异常"]
    evidence_items = cast(list[dict[str, object]], payload["confirmed_evidence"])
    assert evidence_items[0]["source"] == "doris_sql"
    assert payload["unknowns"] == ["尚未确认 Spring API 缓存状态"]
