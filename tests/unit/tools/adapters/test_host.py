from datetime import UTC, datetime

from datasentry.tools.adapters.host import HostStatusTool, ServiceStatusTool
from datasentry.tools.transports.ssh import SshCommandId

NOW = datetime(2026, 6, 25, 12, 0, tzinfo=UTC)


class FixtureSshTransport:
    def execute(
        self,
        target: str,
        command_id: SshCommandId,
        arguments: tuple[str, ...] = (),
    ) -> str:
        del target
        outputs = {
            SshCommandId.HOST_UPTIME: "up 2 days, 3 hours\n",
            SshCommandId.HOST_MEMORY: (
                "Mem: 16000000000 8000000000 1000000000 1000000000 7000000000 7000000000\n"
            ),
            SshCommandId.HOST_FILESYSTEM: (
                "/dev/vda1 100000000000 50000000000 50000000000 50% /\n"
                "/dev/vdb1 200000000000 180000000000 20000000000 90% /data\n"
            ),
            SshCommandId.HOST_INODES: ("/dev/vda1 10000000 100000 9900000 1% /\n"),
            SshCommandId.HOST_TIME: "yes\n",
            SshCommandId.SERVICE_STATUS: (
                "active\n" if arguments == ("mysql",) else "not_running\n"
            ),
        }
        return outputs[command_id]


def _fact(observations: list, metric: str):
    return next(item for item in observations if item.metric_or_fact == metric)


def test_host_status_maps_bounded_resource_facts() -> None:
    observations = HostStatusTool(
        FixtureSshTransport(),
        clock=lambda: NOW,
    ).execute(
        inspection_id="inspection-1",
        target="data1",
        arguments={},
    )

    assert _fact(observations, "host_uptime_seconds").value == 183600
    assert _fact(observations, "host_memory").value["total_bytes"] == 16000000000
    assert len(_fact(observations, "host_filesystems").value) == 2
    assert _fact(observations, "host_time_synchronized").value is True


def test_service_status_uses_allowlisted_service() -> None:
    tool = ServiceStatusTool(FixtureSshTransport(), clock=lambda: NOW)

    mysql = tool.execute(
        inspection_id="inspection-1",
        target="data1",
        arguments={"service": "mysql"},
    )
    collector = tool.execute(
        inspection_id="inspection-1",
        target="data1",
        arguments={"service": "collector"},
    )

    assert _fact(mysql, "service_state").value == {"state": "RUNNING"}
    assert _fact(collector, "service_state").value == {"state": "NOT_RUNNING"}
