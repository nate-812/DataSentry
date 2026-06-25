"""Kafka 固定 CLI 输出到标准 Observation 的映射。"""

import re
import time
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Literal, Protocol, cast

from pydantic import BaseModel, JsonValue, ValidationError

from datasentry.domain import Observation, ToolName
from datasentry.domain.common import utc_now
from datasentry.tools.errors import ToolError
from datasentry.tools.transports.ssh import SshCommandId

ALLOWED_TOPICS = (
    "binance.trade.raw",
    "binance.depth.raw",
    "streamlake.whale.alert",
)
ALLOWED_GROUPS = (
    "flink-kline-group",
    "flink-cep-group",
    "flink-risk-group",
)


class TextSshTransport(Protocol):
    def execute(
        self,
        target: str,
        command_id: SshCommandId,
        arguments: tuple[str, ...] = (),
    ) -> str:
        raise NotImplementedError  # pragma: no cover


class TopicArguments(BaseModel):
    topic: Literal[
        "binance.trade.raw",
        "binance.depth.raw",
        "streamlake.whale.alert",
    ]


class GroupArguments(BaseModel):
    group: Literal[
        "flink-kline-group",
        "flink-cep-group",
        "flink-risk-group",
    ]


def _offsets(value: str) -> dict[str, JsonValue]:
    offsets: dict[str, JsonValue] = {}
    for line in value.splitlines():
        fields = line.rsplit(":", 2)
        if len(fields) != 3 or not fields[1].isdigit() or not fields[2].isdigit():
            continue
        offsets[fields[1]] = int(fields[2])
    if not offsets:
        raise ToolError(
            code="tool.parse_failed",
            message="Kafka Offset 输出无法解析",
        )
    return offsets


class _KafkaTool:
    def __init__(
        self,
        transport: TextSshTransport,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._transport = transport
        self._clock = clock

    def _observation(
        self,
        inspection_id: str,
        target: str,
        metric_or_fact: str,
        value: JsonValue,
    ) -> Observation:
        return Observation(
            inspection_id=inspection_id,
            component="kafka",
            metric_or_fact=metric_or_fact,
            value=value,
            source="kafka_cli_readonly",
            target=target,
            observed_at=self._clock(),
        )


class KafkaTopicsTool(_KafkaTool):
    name = ToolName.GET_KAFKA_TOPICS

    def execute(
        self,
        *,
        inspection_id: str,
        target: str,
        arguments: Mapping[str, JsonValue],
    ) -> list[Observation]:
        if arguments:
            raise ToolError(
                code="tool.invalid_arguments",
                message="Kafka Topic 列表工具不接受参数",
            )
        visible = {
            line.strip()
            for line in self._transport.execute(
                target,
                SshCommandId.KAFKA_TOPICS,
            ).splitlines()
            if line.strip()
        }
        topics = sorted(topic for topic in ALLOWED_TOPICS if topic in visible)
        broker = self._transport.execute(target, SshCommandId.KAFKA_BROKER).strip()
        return [
            self._observation(
                inspection_id,
                target,
                "topics",
                cast(JsonValue, topics),
            ),
            self._observation(
                inspection_id,
                target,
                "broker_state",
                {"state": "RUNNING" if broker else "UNKNOWN"},
            ),
        ]


class KafkaTopicTool(_KafkaTool):
    name = ToolName.GET_KAFKA_TOPIC

    def __init__(
        self,
        transport: TextSshTransport,
        *,
        clock: Callable[[], datetime] = utc_now,
        sleeper: Callable[[float], None] = time.sleep,
        sample_interval_seconds: float = 1.0,
    ) -> None:
        super().__init__(transport, clock=clock)
        self._sleeper = sleeper
        self._sample_interval_seconds = sample_interval_seconds

    def execute(
        self,
        *,
        inspection_id: str,
        target: str,
        arguments: Mapping[str, JsonValue],
    ) -> list[Observation]:
        try:
            topic = TopicArguments.model_validate(arguments).topic
        except ValidationError as error:
            raise ToolError(
                code="tool.invalid_arguments",
                message="Kafka Topic 参数无效",
            ) from error
        describe = self._transport.execute(
            target,
            SshCommandId.KAFKA_TOPIC_DESCRIBE,
            (topic,),
        )
        first = _offsets(
            self._transport.execute(
                target,
                SshCommandId.KAFKA_OFFSETS,
                (topic,),
            )
        )
        self._sleeper(self._sample_interval_seconds)
        second = _offsets(
            self._transport.execute(
                target,
                SshCommandId.KAFKA_OFFSETS,
                (topic,),
            )
        )
        advancing = any(
            isinstance(value, int)
            and isinstance(first.get(partition), int)
            and value > cast(int, first[partition])
            for partition, value in second.items()
        )
        partition_count_match = re.search(r"PartitionCount:\s*(\d+)", describe)
        partition_count = (
            None if partition_count_match is None else int(partition_count_match.group(1))
        )
        return [
            self._observation(
                inspection_id,
                target,
                "topic_advancing",
                advancing,
            ),
            self._observation(
                inspection_id,
                target,
                "topic_partition_end_offsets",
                second,
            ),
            self._observation(
                inspection_id,
                target,
                "topic_partition_count",
                partition_count,
            ),
        ]


class KafkaGroupTool(_KafkaTool):
    name = ToolName.GET_KAFKA_GROUP

    def execute(
        self,
        *,
        inspection_id: str,
        target: str,
        arguments: Mapping[str, JsonValue],
    ) -> list[Observation]:
        try:
            group = GroupArguments.model_validate(arguments).group
        except ValidationError as error:
            raise ToolError(
                code="tool.invalid_arguments",
                message="Kafka Consumer Group 参数无效",
            ) from error
        output = self._transport.execute(
            target,
            SshCommandId.KAFKA_GROUP,
            (group,),
        )
        not_visible = "does not exist" in output.casefold() or not output.strip()
        observations = [
            self._observation(
                inspection_id,
                target,
                "consumer_group_visibility",
                {
                    "group": group,
                    "state": "NOT_VISIBLE" if not_visible else "VISIBLE",
                },
            )
        ]
        if not not_visible:
            lag_values = [
                int(match.group(1))
                for line in output.splitlines()
                if (match := re.search(r"\s(\d+)\s*$", line)) is not None
            ]
            if lag_values:
                observations.append(
                    self._observation(
                        inspection_id,
                        target,
                        "consumer_group_lag",
                        sum(lag_values),
                    )
                )
        return observations
