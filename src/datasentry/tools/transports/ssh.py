"""严格 host key 校验和固定命令目录的 SSH 传输。"""

import re
from collections.abc import Callable, Mapping
from enum import StrEnum
from pathlib import Path
from typing import Protocol

import paramiko

from datasentry.tools.errors import ToolError
from datasentry.tools.targets import (
    EnvironmentSecretResolver,
    HostTarget,
    SshTarget,
    ToolLimits,
)


class ReadableStream(Protocol):
    def read(self, size: int) -> bytes:
        raise NotImplementedError  # pragma: no cover


class SshClient(Protocol):
    def load_host_keys(self, filename: str) -> None:
        raise NotImplementedError  # pragma: no cover

    def set_missing_host_key_policy(self, policy: object) -> None:
        raise NotImplementedError  # pragma: no cover

    def connect(self, **kwargs: object) -> None:
        raise NotImplementedError  # pragma: no cover

    def exec_command(
        self,
        command: str,
        timeout: float,
    ) -> tuple[object, ReadableStream, ReadableStream]:
        raise NotImplementedError  # pragma: no cover

    def close(self) -> None:
        raise NotImplementedError  # pragma: no cover


class SshCommandId(StrEnum):
    HOST_UPTIME = "host_uptime"
    HOST_MEMORY = "host_memory"
    HOST_FILESYSTEM = "host_filesystem"
    HOST_INODES = "host_inodes"
    HOST_TIME = "host_time"
    SERVICE_STATUS = "service_status"
    KAFKA_TOPICS = "kafka_topics"
    KAFKA_TOPIC_DESCRIBE = "kafka_topic_describe"
    KAFKA_OFFSETS = "kafka_offsets"
    KAFKA_GROUP = "kafka_group"
    KAFKA_BROKER = "kafka_broker"
    RECENT_JOURNAL = "recent_journal"
    RECENT_FILE = "recent_file"


STATIC_COMMANDS = {
    SshCommandId.HOST_UPTIME: "uptime -p",
    SshCommandId.HOST_MEMORY: "free -b",
    SshCommandId.HOST_FILESYSTEM: ("df -B1 --output=source,size,used,avail,pcent,target"),
    SshCommandId.HOST_INODES: ("df -i --output=source,itotal,iused,iavail,ipcent,target"),
    SshCommandId.HOST_TIME: ("timedatectl show --property=NTPSynchronized --value"),
    SshCommandId.KAFKA_TOPICS: (
        "/opt/kafka/bin/kafka-topics.sh --bootstrap-server 127.0.0.1:9092 --list"
    ),
    SshCommandId.KAFKA_BROKER: (
        "/opt/kafka/bin/kafka-broker-api-versions.sh --bootstrap-server 127.0.0.1:9092"
    ),
}
SERVICE_COMMANDS = {
    "mysql": "systemctl is-active mysql",
    "redis": "systemctl is-active redis-server",
    "kafka": "pgrep -f -- 'kafka.Kafka'",
    "flink_jobmanager": "pgrep -f -- 'StandaloneSessionClusterEntrypoint'",
    "flink_taskmanager": "pgrep -f -- 'TaskManagerRunner'",
    "doris_fe": "pgrep -f -- 'DorisFE'",
    "doris_be": "pgrep -f -- 'doris_be'",
    "collector": "pgrep -f -- 'python main.py'",
    "spring_api": "pgrep -f -- 'java -jar'",
    "ai_engine": "pgrep -f -- 'uvicorn main:app'",
}
SAFE_KAFKA_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
SAFE_UNIT = re.compile(r"^[A-Za-z0-9_.@-]+$")
ALLOWED_LOG_ROOTS = (Path("/opt"), Path("/var/log"), Path("/srv"))


def _command(command_id: SshCommandId, arguments: tuple[str, ...]) -> str:
    if command_id in STATIC_COMMANDS:
        if arguments:
            raise ToolError(
                code="tool.invalid_arguments",
                message="固定 SSH 命令不接受参数",
            )
        return STATIC_COMMANDS[command_id]
    if command_id is SshCommandId.SERVICE_STATUS:
        if len(arguments) != 1 or arguments[0] not in SERVICE_COMMANDS:
            raise ToolError(
                code="tool.invalid_arguments",
                message="服务状态参数不在白名单",
            )
        return SERVICE_COMMANDS[arguments[0]]
    if command_id in {
        SshCommandId.KAFKA_TOPIC_DESCRIBE,
        SshCommandId.KAFKA_OFFSETS,
        SshCommandId.KAFKA_GROUP,
    }:
        if len(arguments) != 1 or SAFE_KAFKA_NAME.fullmatch(arguments[0]) is None:
            raise ToolError(
                code="tool.invalid_arguments",
                message="Kafka 参数不在白名单格式",
            )
        value = arguments[0]
        if command_id is SshCommandId.KAFKA_TOPIC_DESCRIBE:
            return (
                "/opt/kafka/bin/kafka-topics.sh --bootstrap-server "
                f"127.0.0.1:9092 --describe --topic {value}"
            )
        if command_id is SshCommandId.KAFKA_OFFSETS:
            return (
                "/opt/kafka/bin/kafka-get-offsets.sh --bootstrap-server "
                f"127.0.0.1:9092 --topic {value}"
            )
        return (
            "/opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server "
            f"127.0.0.1:9092 --describe --group {value}"
        )
    if command_id is SshCommandId.RECENT_JOURNAL:
        if (
            len(arguments) != 3
            or SAFE_UNIT.fullmatch(arguments[0]) is None
            or not all(item.isdigit() for item in arguments[1:])
        ):
            raise ToolError(
                code="tool.invalid_arguments",
                message="journal 日志参数无效",
            )
        unit, minutes, lines = arguments
        return f"journalctl --no-pager --utc --since '-{minutes} minutes' -n {lines} -u {unit}"
    if command_id is SshCommandId.RECENT_FILE:
        if len(arguments) != 2 or not arguments[1].isdigit():
            raise ToolError(
                code="tool.invalid_arguments",
                message="文件日志参数无效",
            )
        path = Path(arguments[0])
        resolved = path.resolve()
        if not path.is_absolute() or not any(
            resolved.is_relative_to(root.resolve()) for root in ALLOWED_LOG_ROOTS
        ):
            raise ToolError(
                code="tool.policy_denied",
                message="日志路径不在允许目录",
            )
        return f"tail -n {arguments[1]} -- {path}"
    raise ToolError(
        code="tool.policy_denied",
        message="SSH 命令未进入白名单",
    )


class SshTransport:
    """通过固定命令目录执行只读 SSH 查询。"""

    def __init__(
        self,
        *,
        hosts: Mapping[str, HostTarget],
        targets: Mapping[str, SshTarget],
        limits: ToolLimits,
        secrets: EnvironmentSecretResolver,
        client_factory: Callable[[], SshClient] = paramiko.SSHClient,
    ) -> None:
        self._hosts = dict(hosts)
        self._targets = dict(targets)
        self._limits = limits
        self._secrets = secrets
        self._client_factory = client_factory

    def execute(
        self,
        target: str,
        command_id: SshCommandId,
        arguments: tuple[str, ...] = (),
    ) -> str:
        configured = self._targets.get(target)
        if configured is None or configured.host not in self._hosts:
            raise ToolError(
                code="tool.configuration",
                message="SSH 目标未配置",
            )
        if not configured.known_hosts.is_file():
            raise ToolError(
                code="tool.configuration",
                message="SSH known_hosts 不存在",
            )
        command = _command(command_id, arguments)
        client = self._client_factory()
        try:
            client.load_host_keys(str(configured.known_hosts))
            client.set_missing_host_key_policy(paramiko.RejectPolicy())
            kwargs: dict[str, object] = {
                "hostname": self._hosts[configured.host].address,
                "port": configured.port,
                "username": configured.username,
                "timeout": self._limits.connect_timeout_seconds,
                "banner_timeout": self._limits.connect_timeout_seconds,
                "auth_timeout": self._limits.connect_timeout_seconds,
                "look_for_keys": False,
                "allow_agent": False,
            }
            if configured.password_env is not None:
                kwargs["password"] = self._secrets.require(configured.password_env)
            if configured.private_key_path is not None:
                kwargs["key_filename"] = str(configured.private_key_path)
            client.connect(**kwargs)
            _, stdout, stderr = client.exec_command(
                command,
                timeout=self._limits.read_timeout_seconds,
            )
            limit = self._limits.max_output_bytes
            output = stdout.read(limit + 1)
            error_output = stderr.read(limit + 1)
            if len(output) + len(error_output) > limit:
                raise ToolError(
                    code="tool.output_limit_exceeded",
                    message="SSH 输出超过上限",
                )
            if error_output:
                raise ToolError(
                    code="tool.upstream_error",
                    message="SSH 固定命令返回错误",
                )
            return output.decode("utf-8", errors="replace")
        except ToolError:
            raise
        except paramiko.AuthenticationException as error:
            raise ToolError(
                code="tool.authentication_failed",
                message="SSH 认证失败",
            ) from error
        except TimeoutError as error:
            raise ToolError(
                code="tool.timeout",
                message="SSH 查询超时",
                retryable=True,
            ) from error
        except (OSError, paramiko.SSHException) as error:
            raise ToolError(
                code="tool.connection_failed",
                message="SSH 连接失败",
                retryable=True,
            ) from error
        finally:
            client.close()
