import json
import logging

import pytest

from datasentry.logging import configure_logging, get_logger, redact_sensitive_values


def test_redact_sensitive_values_recursively() -> None:
    event = {
        "token": "secret-token",
        "nested": {
            "authorization": "Bearer abc",
            "component": "flink",
        },
        "items": [{"password": "secret-password"}],
        "tuple": ({"api_key": "secret-key"}, "visible"),
    }

    assert redact_sensitive_values(event) == {
        "token": "[已脱敏]",
        "nested": {
            "authorization": "[已脱敏]",
            "component": "flink",
        },
        "items": [{"password": "[已脱敏]"}],
        "tuple": ({"api_key": "[已脱敏]"}, "visible"),
    }


def test_configure_logging_emits_redacted_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(level="INFO", log_format="json")

    get_logger("test").info(
        "inspection.created",
        component="datasentry",
        token="secret-token",
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.err)
    assert payload["event"] == "inspection.created"
    assert payload["level"] == "info"
    assert payload["component"] == "datasentry"
    assert payload["token"] == "[已脱敏]"
    assert "timestamp" in payload

    logging.shutdown()
