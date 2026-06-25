from datasentry.tools.redaction import redact_text, redact_value


def test_redact_value_masks_nested_secret_keys_and_url_credentials() -> None:
    value = {
        "password": "p@ss",
        "nested": {"access_key": "AK123", "safe": "ok"},
        "url": "http://user:token@example.test/path",
    }

    assert redact_value(value) == {
        "password": "[REDACTED]",
        "nested": {"access_key": "[REDACTED]", "safe": "ok"},
        "url": "http://[REDACTED]@example.test/path",
    }


def test_redact_text_masks_headers_assignments_and_private_key_blocks() -> None:
    text = """
Authorization: Bearer token-value
password=super-secret
Cookie: session=abc
-----BEGIN PRIVATE KEY-----
private-material
-----END PRIVATE KEY-----
"""

    redacted = redact_text(text)

    assert "token-value" not in redacted
    assert "super-secret" not in redacted
    assert "session=abc" not in redacted
    assert "private-material" not in redacted
    assert redacted.count("[REDACTED]") >= 4
