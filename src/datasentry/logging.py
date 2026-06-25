"""Structured logging with recursive secret redaction."""

import logging
import sys
from collections.abc import Mapping, MutableMapping
from typing import Literal, cast

import structlog

SENSITIVE_KEYS = frozenset(
    {
        "access_key",
        "api_key",
        "authorization",
        "cookie",
        "password",
        "private_key",
        "secret",
        "secret_key",
        "token",
    }
)


def redact_sensitive_values(
    value: object,
    *,
    parent_key: str | None = None,
) -> object:
    """Return a recursively redacted copy of a structured value."""
    if parent_key is not None and parent_key.lower() in SENSITIVE_KEYS:
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {
            str(key): redact_sensitive_values(item, parent_key=str(key))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive_values(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive_values(item) for item in value)
    return value


def _redact_event(
    logger: object,
    method_name: str,
    event_dict: MutableMapping[str, object],
) -> MutableMapping[str, object]:
    del logger, method_name
    redacted = redact_sensitive_values(event_dict)
    if not isinstance(redacted, MutableMapping):
        raise TypeError("structured log event must be a mutable mapping")
    return redacted


def configure_logging(*, level: str, log_format: Literal["json", "console"]) -> None:
    """Configure structlog and the standard-library logging bridge."""
    renderer: structlog.types.Processor
    if log_format == "json":
        renderer = structlog.processors.JSONRenderer(sort_keys=True)
    else:
        renderer = structlog.dev.ConsoleRenderer()

    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, level),
        stream=sys.stderr,
        force=True,
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _redact_event,
            renderer,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a configured structured logger."""
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))
