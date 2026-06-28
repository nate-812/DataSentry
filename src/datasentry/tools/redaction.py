"""工具模块兼容的脱敏导出。"""

from datasentry.redaction import REDACTED, redact_text, redact_value

__all__ = [
    "REDACTED",
    "redact_text",
    "redact_value",
]
