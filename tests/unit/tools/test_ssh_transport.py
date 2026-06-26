from pathlib import Path

import pytest

from datasentry.tools.errors import ToolError
from datasentry.tools.targets import (
    EnvironmentSecretResolver,
    HostTarget,
    SshTarget,
    ToolLimits,
)
from datasentry.tools.transports.ssh import SshCommandId, SshTransport, _command


class FakeStream:
    def __init__(self, value: bytes) -> None:
        self._value = value

    def read(self, size: int) -> bytes:
        return self._value[:size]


class FakeClient:
    def __init__(self, stdout: bytes = b"ok\n", stderr: bytes = b"") -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.loaded_host_keys: str | None = None
        self.policy: object | None = None
        self.command: str | None = None

    def load_host_keys(self, filename: str) -> None:
        self.loaded_host_keys = filename

    def set_missing_host_key_policy(self, policy: object) -> None:
        self.policy = policy

    def connect(self, **kwargs: object) -> None:
        del kwargs

    def exec_command(
        self,
        command: str,
        timeout: float,
    ) -> tuple[None, FakeStream, FakeStream]:
        del timeout
        self.command = command
        return None, FakeStream(self.stdout), FakeStream(self.stderr)

    def close(self) -> None:
        return None


class RaisingClient(FakeClient):
    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error = error

    def connect(self, **kwargs: object) -> None:
        del kwargs
        raise self.error


def _transport(tmp_path: Path, client: FakeClient) -> SshTransport:
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text("fixture", encoding="utf-8")
    return SshTransport(
        hosts={"data1": HostTarget(address="192.0.2.10")},
        targets={
            "data1": SshTarget(
                host="data1",
                username="readonly",
                password_env="TEST_SSH_PASSWORD",
                known_hosts=known_hosts,
            )
        },
        limits=ToolLimits(max_output_bytes=1024),
        secrets=EnvironmentSecretResolver(),
        client_factory=lambda: client,
    )


def test_ssh_transport_uses_reject_policy_and_fixed_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_SSH_PASSWORD", "secret")
    client = FakeClient()

    output = _transport(tmp_path, client).execute(
        "data1",
        SshCommandId.HOST_TIME,
    )

    assert output == "ok\n"
    assert client.loaded_host_keys is not None
    assert type(client.policy).__name__ == "RejectPolicy"
    assert client.command == "timedatectl show --property=NTPSynchronized --value"


def test_ssh_inode_command_uses_portable_df_syntax() -> None:
    command = _command(SshCommandId.HOST_INODES, ())

    assert command == "df -i"


def test_ssh_transport_rejects_missing_known_hosts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_SSH_PASSWORD", "secret")
    target = SshTarget(
        host="data1",
        username="readonly",
        password_env="TEST_SSH_PASSWORD",
        known_hosts=tmp_path / "missing",
    )
    transport = SshTransport(
        hosts={"data1": HostTarget(address="192.0.2.10")},
        targets={"data1": target},
        limits=ToolLimits(),
        secrets=EnvironmentSecretResolver(),
        client_factory=FakeClient,
    )

    with pytest.raises(ToolError) as raised:
        transport.execute("data1", SshCommandId.HOST_TIME)

    assert raised.value.code == "tool.configuration"


def test_ssh_transport_rejects_oversized_combined_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_SSH_PASSWORD", "secret")
    client = FakeClient(stdout=b"x" * 1025)

    with pytest.raises(ToolError) as raised:
        _transport(tmp_path, client).execute("data1", SshCommandId.HOST_TIME)

    assert raised.value.code == "tool.output_limit_exceeded"


@pytest.mark.parametrize(
    ("command_id", "arguments", "fragment"),
    [
        (SshCommandId.SERVICE_STATUS, ("mysql",), "systemctl is-active mysql"),
        (
            SshCommandId.KAFKA_TOPIC_DESCRIBE,
            ("binance.trade.raw",),
            "--describe --topic binance.trade.raw",
        ),
        (
            SshCommandId.KAFKA_OFFSETS,
            ("binance.trade.raw",),
            "--topic binance.trade.raw",
        ),
        (
            SshCommandId.KAFKA_GROUP,
            ("flink-kline-group",),
            "--describe --group flink-kline-group",
        ),
        (
            SshCommandId.RECENT_JOURNAL,
            ("spring.service", "30", "200"),
            "journalctl",
        ),
        (
            SshCommandId.RECENT_FILE,
            ("/var/log/app.log", "200"),
            "tail -n 200",
        ),
    ],
)
def test_ssh_command_catalog_maps_allowlisted_arguments(
    command_id: SshCommandId,
    arguments: tuple[str, ...],
    fragment: str,
) -> None:
    assert fragment in _command(command_id, arguments)


@pytest.mark.parametrize(
    ("command_id", "arguments"),
    [
        (SshCommandId.HOST_TIME, ("extra",)),
        (SshCommandId.SERVICE_STATUS, ("unknown",)),
        (SshCommandId.KAFKA_GROUP, ("bad;group",)),
        (SshCommandId.RECENT_JOURNAL, ("bad unit", "30", "200")),
        (SshCommandId.RECENT_FILE, ("../../etc/passwd", "200")),
    ],
)
def test_ssh_command_catalog_rejects_unsafe_arguments(
    command_id: SshCommandId,
    arguments: tuple[str, ...],
) -> None:
    with pytest.raises(ToolError):
        _command(command_id, arguments)


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (TimeoutError(), "tool.timeout"),
        (OSError(), "tool.connection_failed"),
    ],
)
def test_ssh_transport_maps_connection_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    code: str,
) -> None:
    monkeypatch.setenv("TEST_SSH_PASSWORD", "secret")

    with pytest.raises(ToolError) as raised:
        _transport(tmp_path, RaisingClient(error)).execute(
            "data1",
            SshCommandId.HOST_TIME,
        )

    assert raised.value.code == code


def test_ssh_transport_rejects_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_SSH_PASSWORD", "secret")

    with pytest.raises(ToolError) as raised:
        _transport(tmp_path, FakeClient(stderr=b"failure")).execute(
            "data1",
            SshCommandId.HOST_TIME,
        )

    assert raised.value.code == "tool.upstream_error"
