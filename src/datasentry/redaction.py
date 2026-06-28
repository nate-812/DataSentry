"""通用脱敏工具。"""

import re
from collections.abc import Mapping, Sequence
from typing import cast
from urllib.parse import urlsplit, urlunsplit

from pydantic import JsonValue

REDACTED = "[REDACTED]"
SECRET_KEYS = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "access_key",
        "accesskey",
        "secret_key",
        "secretkey",
        "ak",
        "sk",
        "authorization",
        "cookie",
    }
)
ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(password|passwd|secret|token|access[_-]?key|secret[_-]?key|ak|sk)"
    r"\s*[:=]\s*[^\s,;]+"
)
AUTHORIZATION_PATTERN = re.compile(r"(?i)\bAuthorization\s*:\s*Bearer\s+\S+")
COOKIE_PATTERN = re.compile(r"(?i)\bCookie\s*:\s*[^\r\n]+")
PRIVATE_KEY_PATTERN = re.compile(
    r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----",
    re.DOTALL,
)


def _normalized_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.casefold()).strip("_")


def _redact_url_credentials(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https", "mysql", "redis"} or parsed.hostname is None:
        return value
    if parsed.username is None and parsed.password is None:
        return value
    host = parsed.hostname
    if ":" in host:
        host = f"[{host}]"
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    return urlunsplit(
        (
            parsed.scheme,
            f"{REDACTED}@{host}",
            parsed.path,
            parsed.query,
            parsed.fragment,
        )
    )


def redact_text(value: str) -> str:
    """遮蔽常见秘密赋值、认证头、Cookie、URL 凭据和私钥区块。"""
    redacted = PRIVATE_KEY_PATTERN.sub(REDACTED, value)
    redacted = AUTHORIZATION_PATTERN.sub(f"Authorization: {REDACTED}", redacted)
    redacted = COOKIE_PATTERN.sub(f"Cookie: {REDACTED}", redacted)
    redacted = ASSIGNMENT_PATTERN.sub(
        lambda match: f"{match.group(1)}={REDACTED}",
        redacted,
    )
    return _redact_url_credentials(redacted)


def redact_value(value: JsonValue | object) -> JsonValue:
    """递归脱敏可序列化结构。"""
    if isinstance(value, Mapping):
        return {
            str(key): (REDACTED if _normalized_key(str(key)) in SECRET_KEYS else redact_value(item))
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact_value(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return cast(JsonValue, value)
