"""本地 live smoke 前的安全配置预检。"""

import os
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from pydantic import Field

from datasentry.domain.common import DomainModel
from datasentry.tools.targets import TargetCatalog

SecretStatus = Literal["configured", "missing"]

CLOUD_VARIABLE_HINTS = {
    "DATASENTRY_DORIS_PASSWORD": "DORIS_PASSWORD",
    "DATASENTRY_MYSQL_PASSWORD": "MYSQL_PASSWORD",
    "DATASENTRY_REDIS_PASSWORD": "REDIS_PASSWORD",
}


class SecretPreflightStatus(DomainModel):
    """单个目标所需 secret 的本地环境状态。"""

    component: str = Field(min_length=1)
    target: str = Field(min_length=1)
    environment_variable: str = Field(min_length=1)
    status: SecretStatus
    required: bool = True
    cloud_variable: str | None = None
    message: str = Field(min_length=1)


class PasswordlessTarget(DomainModel):
    """显式无 password_env 的数据库目标说明。"""

    component: str = Field(min_length=1)
    target: str = Field(min_length=1)
    message: str = Field(min_length=1)


class OpsPreflightReport(DomainModel):
    """live smoke 预检报告，不包含任何 secret 值。"""

    targets_file: str
    secrets: list[SecretPreflightStatus]
    passwordless_targets: list[PasswordlessTarget]
    summary: dict[str, int]


def build_ops_preflight_report(
    *,
    targets: TargetCatalog,
    targets_file: Path,
) -> OpsPreflightReport:
    """从目标目录生成无副作用预检报告。"""
    secrets = list(_iter_secret_statuses(targets))
    configured = sum(1 for item in secrets if item.status == "configured")
    missing = sum(1 for item in secrets if item.status == "missing")
    return OpsPreflightReport(
        targets_file=str(targets_file),
        secrets=secrets,
        passwordless_targets=list(_iter_passwordless_targets(targets)),
        summary={
            "configured": configured,
            "missing": missing,
            "total": len(secrets),
        },
    )


def _iter_secret_statuses(targets: TargetCatalog) -> Iterable[SecretPreflightStatus]:
    for target, ssh_target in sorted(targets.ssh.items()):
        if ssh_target.password_env is not None:
            yield _secret_status(
                component="ssh",
                target=target,
                environment_variable=ssh_target.password_env,
            )
    for target, mysql_target in sorted(targets.mysql.items()):
        if mysql_target.password_env is not None:
            yield _secret_status(
                component="mysql",
                target=target,
                environment_variable=mysql_target.password_env,
            )
    for target, redis_target in sorted(targets.redis.items()):
        yield _secret_status(
            component="redis",
            target=target,
            environment_variable=redis_target.password_env,
        )


def _secret_status(
    *,
    component: str,
    target: str,
    environment_variable: str,
) -> SecretPreflightStatus:
    configured = bool(os.environ.get(environment_variable))
    status: SecretStatus = "configured" if configured else "missing"
    if configured:
        message = f"{environment_variable} 已在当前进程环境中设置。"
    else:
        message = f"本地进程缺少 {environment_variable}，该目标在触网前会返回配置缺失。"
    return SecretPreflightStatus(
        component=component,
        target=target,
        environment_variable=environment_variable,
        status=status,
        required=True,
        cloud_variable=CLOUD_VARIABLE_HINTS.get(environment_variable),
        message=message,
    )


def _iter_passwordless_targets(targets: TargetCatalog) -> Iterable[PasswordlessTarget]:
    for target, mysql_target in sorted(targets.mysql.items()):
        if mysql_target.password_env is None:
            yield PasswordlessTarget(
                component="mysql",
                target=target,
                message="该数据库目标未声明 password_env，将使用空密码发起只读连接。",
            )
