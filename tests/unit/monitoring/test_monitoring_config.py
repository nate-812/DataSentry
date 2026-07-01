from pathlib import Path

import pytest

from datasentry.errors import DataSentryError
from datasentry.monitoring import load_monitoring_deployment_config


def test_load_monitoring_deployment_config_from_example() -> None:
    config = load_monitoring_deployment_config(Path("config/monitoring.example.toml"))

    assert str(config.endpoints.prometheus_base_url) == "http://prometheus.example:9090"
    assert str(config.endpoints.grafana_base_url) == "http://grafana.example:3000"
    assert str(config.endpoints.alertmanager_base_url) == "http://alertmanager.example:9093"
    assert str(config.endpoints.datasentry_api_base_url) == "http://datasentry.example:8000"
    assert "KlineFreshnessStale" in config.endpoints.expected_alerts


def test_monitoring_config_rejects_urls_with_credentials(tmp_path: Path) -> None:
    config_path = tmp_path / "monitoring.toml"
    config_path.write_text(
        """
[endpoints]
prometheus_base_url = "http://user:password@prometheus.example:9090"
grafana_base_url = "http://grafana.example:3000"
alertmanager_base_url = "http://alertmanager.example:9093"
datasentry_api_base_url = "http://datasentry.example:8000"
expected_alerts = ["KlineFreshnessStale"]
""",
        encoding="utf-8",
    )

    with pytest.raises(DataSentryError) as error:
        load_monitoring_deployment_config(config_path)

    assert error.value.code == "configuration.monitoring_invalid"
    assert error.value.message == "监控部署配置无效"
