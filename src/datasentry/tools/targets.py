"""从本地 TOML 加载无秘密的生产目标目录。"""

import os
import re
import tomllib
from pathlib import Path
from typing import Self
from urllib.parse import urlsplit

from pydantic import Field, ValidationError, field_validator, model_validator

from datasentry.domain.common import DomainModel
from datasentry.errors import ConfigurationError

ENVIRONMENT_NAME_PATTERN = r"^[A-Z][A-Z0-9_]+$"
ALLOWED_LOG_ROOTS = (Path("/opt"), Path("/var/log"), Path("/srv"))


class ToolLimits(DomainModel):
    """所有真实只读工具共享的安全上限。"""

    connect_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    read_timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    max_output_bytes: int = Field(default=65_536, ge=1_024, le=1_048_576)
    max_log_lines: int = Field(default=200, ge=1, le=200)
    max_log_minutes: int = Field(default=30, ge=1, le=30)
    retry_attempts: int = Field(default=1, ge=0, le=1)


class HostTarget(DomainModel):
    address: str = Field(min_length=1)


class SshTarget(DomainModel):
    host: str = Field(min_length=1)
    port: int = Field(default=22, ge=1, le=65_535)
    username: str = Field(min_length=1)
    password_env: str | None = Field(default=None, pattern=ENVIRONMENT_NAME_PATTERN)
    private_key_path: Path | None = None
    known_hosts: Path

    @model_validator(mode="after")
    def validate_authentication_and_host_keys(self) -> Self:
        if not str(self.known_hosts):
            raise ValueError("known_hosts 不能为空")
        if not self.known_hosts.is_absolute():
            raise ValueError("known_hosts 必须是绝对路径")
        if self.password_env is None and self.private_key_path is None:
            raise ValueError("SSH 必须配置密码环境变量或私钥路径")
        if self.private_key_path is not None and not self.private_key_path.is_absolute():
            raise ValueError("SSH 私钥路径必须是绝对路径")
        return self


class HttpTarget(DomainModel):
    base_url: str = Field(min_length=1)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
            raise ValueError("HTTP base_url 必须是 http 或 https URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("HTTP base_url 不能包含凭据")
        if parsed.query or parsed.fragment:
            raise ValueError("HTTP base_url 不能包含查询参数或 fragment")
        return value.rstrip("/")


class MySqlTarget(DomainModel):
    host: str = Field(min_length=1)
    port: int = Field(ge=1, le=65_535)
    database: str = Field(min_length=1)
    username: str = Field(min_length=1)
    password_env: str = Field(pattern=ENVIRONMENT_NAME_PATTERN)
    timezone: str = Field(default="UTC", min_length=1)


class RedisTarget(DomainModel):
    host: str = Field(min_length=1)
    port: int = Field(ge=1, le=65_535)
    database: int = Field(default=0, ge=0)
    username: str | None = None
    password_env: str = Field(pattern=ENVIRONMENT_NAME_PATTERN)


class LogSource(DomainModel):
    host: str = Field(min_length=1)
    kind: str = Field(pattern=r"^(journal|file)$")
    unit: str | None = None
    path: Path | None = None

    @model_validator(mode="after")
    def validate_source(self) -> Self:
        if self.kind == "journal" and (self.unit is None or self.path is not None):
            raise ValueError("journal 日志源必须只配置 unit")
        if self.kind == "file":
            if self.path is None or self.unit is not None:
                raise ValueError("file 日志源必须只配置 path")
            resolved = self.path.resolve()
            if not self.path.is_absolute() or not any(
                resolved.is_relative_to(root.resolve()) for root in ALLOWED_LOG_ROOTS
            ):
                raise ValueError("日志路径不在允许目录")
        return self


class TargetCatalog(DomainModel):
    """经过交叉引用校验的工具目标目录。"""

    limits: ToolLimits = Field(default_factory=ToolLimits)
    hosts: dict[str, HostTarget] = Field(default_factory=dict)
    ssh: dict[str, SshTarget] = Field(default_factory=dict)
    http: dict[str, HttpTarget] = Field(default_factory=dict)
    mysql: dict[str, MySqlTarget] = Field(default_factory=dict)
    redis: dict[str, RedisTarget] = Field(default_factory=dict)
    logs: dict[str, LogSource] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        referenced_hosts = [
            *(target.host for target in self.ssh.values()),
            *(target.host for target in self.mysql.values()),
            *(target.host for target in self.redis.values()),
            *(target.host for target in self.logs.values()),
        ]
        missing = sorted(set(referenced_hosts) - self.hosts.keys())
        if missing:
            raise ConfigurationError(
                code="configuration.target_reference_missing",
                message="目标配置引用了不存在的主机",
                details={"hosts": missing},
            )
        return self

    @classmethod
    def load(cls, path: Path) -> Self:
        """读取 TOML，并将解析或模型错误转换为安全配置异常。"""
        try:
            with path.open("rb") as file:
                return cls.model_validate(tomllib.load(file))
        except ConfigurationError:
            raise
        except (OSError, tomllib.TOMLDecodeError, ValidationError) as error:
            raise ConfigurationError(
                code="configuration.target_invalid",
                message="目标配置 TOML 无效",
                details={"path": str(path)},
            ) from error

    def host(self, alias: str) -> HostTarget:
        return self._lookup(self.hosts, alias, "host")

    def ssh_target(self, alias: str) -> SshTarget:
        return self._lookup(self.ssh, alias, "ssh")

    @staticmethod
    def _lookup[T](values: dict[str, T], alias: str, kind: str) -> T:
        try:
            return values[alias]
        except KeyError as error:
            raise ConfigurationError(
                code="configuration.target_missing",
                message="未找到指定目标",
                details={"kind": kind, "alias": alias},
            ) from error


class EnvironmentSecretResolver:
    """只在连接建立前从进程环境解析秘密。"""

    def require(self, environment_variable: str) -> str:
        if re.fullmatch(ENVIRONMENT_NAME_PATTERN, environment_variable) is None:
            raise ConfigurationError(
                code="configuration.secret_name_invalid",
                message="秘密环境变量名称无效",
            )
        value = os.environ.get(environment_variable)
        if value is None or not value:
            raise ConfigurationError(
                code="configuration.secret_missing",
                message="缺少目标连接所需的秘密环境变量",
                details={"environment_variable": environment_variable},
            )
        return value
