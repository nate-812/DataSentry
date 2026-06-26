"""Alertmanager Webhook 载荷解析。"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from datasentry.errors import DataSentryError
from datasentry.tools.redaction import redact_value


class AlertmanagerAlert(BaseModel):
    """Alertmanager Webhook 中的单条告警。"""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    status: str
    labels: dict[str, str]
    annotations: dict[str, str] = Field(default_factory=dict)
    starts_at: str = Field(alias="startsAt")
    ends_at: str | None = Field(default=None, alias="endsAt")
    generator_url: str | None = Field(default=None, alias="generatorURL")


class AlertmanagerPayload(BaseModel):
    """Alertmanager v4 Webhook 载荷的稳定子集。"""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    receiver: str
    status: str
    group_labels: dict[str, str] = Field(alias="groupLabels")
    common_labels: dict[str, str] = Field(default_factory=dict, alias="commonLabels")
    common_annotations: dict[str, str] = Field(
        default_factory=dict,
        alias="commonAnnotations",
    )
    alerts: tuple[AlertmanagerAlert, ...]
    external_url: str | None = Field(default=None, alias="externalURL")
    version: str | None = None
    group_key: str | None = Field(default=None, alias="groupKey")
    truncated_alerts: int = Field(default=0, alias="truncatedAlerts")

    @property
    def primary_alert(self) -> AlertmanagerAlert:
        """返回告警组中的第一条告警。"""
        return self.alerts[0]


def parse_alertmanager_payload(payload: Any) -> AlertmanagerPayload:
    """解析 Alertmanager Webhook 载荷，失败时返回稳定异常。"""
    try:
        parsed = AlertmanagerPayload.model_validate(payload)
    except ValidationError as error:
        raise DataSentryError(
            code="notification.invalid_payload",
            message="Alertmanager Webhook 载荷无效",
            details={"errors": redact_value(error.errors())},
        ) from error
    if not parsed.alerts:
        raise DataSentryError(
            code="notification.invalid_payload",
            message="Alertmanager Webhook 载荷无效",
            details={"reason": "alerts 不能为空"},
        )
    return parsed
