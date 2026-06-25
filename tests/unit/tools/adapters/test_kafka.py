from datetime import UTC, datetime

import pytest

from datasentry.tools.adapters.kafka import (
    KafkaGroupTool,
    KafkaTopicsTool,
    KafkaTopicTool,
)
from datasentry.tools.errors import ToolError
from datasentry.tools.transports.ssh import SshCommandId

NOW = datetime(2026, 6, 25, 12, 0, tzinfo=UTC)


class FixtureSshTransport:
    offset_calls = 0

    def execute(
        self,
        target: str,
        command_id: SshCommandId,
        arguments: tuple[str, ...] = (),
    ) -> str:
        del target, arguments
        if command_id is SshCommandId.KAFKA_TOPICS:
            return "binance.depth.raw\nbinance.trade.raw\nstreamlake.whale.alert\n"
        if command_id is SshCommandId.KAFKA_TOPIC_DESCRIBE:
            return (
                "Topic: binance.trade.raw PartitionCount: 2 ReplicationFactor: 1\n"
                "Topic: binance.trade.raw Partition: 0 Leader: 1 Replicas: 1 Isr: 1\n"
                "Topic: binance.trade.raw Partition: 1 Leader: 1 Replicas: 1 Isr: 1\n"
            )
        if command_id is SshCommandId.KAFKA_OFFSETS:
            self.offset_calls += 1
            if self.offset_calls == 1:
                return "binance.trade.raw:0:100\nbinance.trade.raw:1:200\n"
            return "binance.trade.raw:0:102\nbinance.trade.raw:1:205\n"
        if command_id is SshCommandId.KAFKA_GROUP:
            return "Error: Consumer group 'flink-kline-group' does not exist.\n"
        return "broker-ok\n"


def _fact(observations: list, metric: str):
    return next(item for item in observations if item.metric_or_fact == metric)


def test_kafka_topics_returns_allowlisted_visible_topics() -> None:
    observations = KafkaTopicsTool(
        FixtureSshTransport(),
        clock=lambda: NOW,
    ).execute(
        inspection_id="inspection-1",
        target="data1",
        arguments={},
    )

    assert _fact(observations, "topics").value == [
        "binance.depth.raw",
        "binance.trade.raw",
        "streamlake.whale.alert",
    ]


def test_kafka_topic_samples_offsets_and_reports_advancing() -> None:
    transport = FixtureSshTransport()
    transport.offset_calls = 0
    observations = KafkaTopicTool(
        transport,
        clock=lambda: NOW,
        sleeper=lambda _: None,
    ).execute(
        inspection_id="inspection-1",
        target="data1",
        arguments={"topic": "binance.trade.raw"},
    )

    assert _fact(observations, "topic_advancing").value is True
    assert _fact(observations, "topic_partition_end_offsets").value == {
        "0": 102,
        "1": 205,
    }


def test_kafka_group_missing_does_not_claim_zero_lag() -> None:
    observations = KafkaGroupTool(
        FixtureSshTransport(),
        clock=lambda: NOW,
    ).execute(
        inspection_id="inspection-1",
        target="data1",
        arguments={"group": "flink-kline-group"},
    )

    assert _fact(observations, "consumer_group_visibility").value == {
        "group": "flink-kline-group",
        "state": "NOT_VISIBLE",
    }
    assert all(item.metric_or_fact != "consumer_group_lag" for item in observations)


def test_kafka_topic_rejects_non_allowlisted_name() -> None:
    with pytest.raises(ToolError) as raised:
        KafkaTopicTool(
            FixtureSshTransport(),
            clock=lambda: NOW,
            sleeper=lambda _: None,
        ).execute(
            inspection_id="inspection-1",
            target="data1",
            arguments={"topic": "binance.trade.raw; rm -rf /"},
        )

    assert raised.value.code == "tool.invalid_arguments"
