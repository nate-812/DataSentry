"""支持递归脱敏的结构化日志。"""

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
    """返回递归脱敏后的结构化数据副本。"""
    if parent_key is not None and parent_key.lower() in SENSITIVE_KEYS:
        return "[已脱敏]"
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
        raise TypeError("结构化日志事件必须是可变映射")
    return redacted


def configure_logging(*, level: str, log_format: Literal["json", "console"]) -> None:
    """配置 structlog 与 Python 标准日志桥接。"""
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
    """返回已配置的结构化 Logger。"""
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))
