"""监控部署验收配置加载。"""

import tomllib
from pathlib import Path
from typing import Self
from urllib.parse import urlsplit

from pydantic import Field, ValidationError, field_validator

from datasentry.domain.common import DomainModel
from datasentry.errors import ConfigurationError


class MonitoringEndpoints(DomainModel):
    """Prometheus/Grafana/Alertmanager/DataSentry 的无凭据端点。"""

    prometheus_base_url: str = Field(min_length=1)
    grafana_base_url: str = Field(min_length=1)
    alertmanager_base_url: str = Field(min_length=1)
    datasentry_api_base_url: str = Field(min_length=1)
    expected_alerts: list[str] = Field(min_length=1)

    @field_validator(
        "prometheus_base_url",
        "grafana_base_url",
        "alertmanager_base_url",
        "datasentry_api_base_url",
    )
    @classmethod
    def validate_safe_base_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
            raise ValueError("监控端点必须是 http 或 https URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("监控端点 URL 不能包含凭据")
        if parsed.query or parsed.fragment:
            raise ValueError("监控端点 URL 不能包含 query 或 fragment")
        return value.rstrip("/")


class MonitoringDeploymentConfig(DomainModel):
    """M8 监控部署验收配置。"""

    endpoints: MonitoringEndpoints

    @classmethod
    def load(cls, path: Path) -> Self:
        """读取 TOML 配置，并将错误归一为安全异常。"""
        try:
            with path.open("rb") as file:
                return cls.model_validate(tomllib.load(file))
        except (OSError, tomllib.TOMLDecodeError, ValidationError) as error:
            raise ConfigurationError(
                code="configuration.monitoring_invalid",
                message="监控部署配置无效",
                details={"path": str(path)},
            ) from error


def load_monitoring_deployment_config(path: Path) -> MonitoringDeploymentConfig:
    """加载 M8 监控部署验收配置。"""
    return MonitoringDeploymentConfig.load(path)
