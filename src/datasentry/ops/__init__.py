"""运维入口的只读预检能力。"""

from datasentry.ops.preflight import (
    OpsPreflightReport,
    PasswordlessTarget,
    SecretPreflightStatus,
    build_ops_preflight_report,
)

__all__ = [
    "OpsPreflightReport",
    "PasswordlessTarget",
    "SecretPreflightStatus",
    "build_ops_preflight_report",
]
