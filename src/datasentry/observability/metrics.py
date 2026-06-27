"""DataSentry 自监控指标注册表。"""

from collections.abc import Mapping
from dataclasses import dataclass

COUNTER_METRICS = frozenset(
    {
        "datasentry_tool_invocations_total",
        "datasentry_tool_failures_total",
        "datasentry_inspections_total",
        "datasentry_inspection_failures_total",
        "datasentry_notification_events_total",
        "datasentry_notification_failures_total",
    }
)

TIMER_METRICS = frozenset({"datasentry_notification_format_seconds"})

LabelKey = tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class CounterSample:
    """计数器指标样本。"""

    name: str
    labels: LabelKey
    value: float


@dataclass(frozen=True)
class TimerSample:
    """耗时指标样本。"""

    name: str
    labels: LabelKey
    count: int
    total_seconds: float


class MetricRegistry:
    """记录 DataSentry 进程内自监控指标。"""

    def __init__(self) -> None:
        self._counters: dict[tuple[str, LabelKey], float] = {}
        self._timers: dict[tuple[str, LabelKey], tuple[int, float]] = {}

    def increment(
        self,
        name: str,
        labels: Mapping[str, str],
        amount: float = 1,
    ) -> None:
        """累加已知计数器指标。"""
        _ensure_metric_name(name, COUNTER_METRICS)
        key = (name, _label_key(labels))
        self._counters[key] = self._counters.get(key, 0) + amount

    def observe_seconds(
        self,
        name: str,
        value: float,
        labels: Mapping[str, str],
    ) -> None:
        """记录已知耗时指标的一次秒级观测。"""
        _ensure_metric_name(name, TIMER_METRICS)
        key = (name, _label_key(labels))
        count, total_seconds = self._timers.get(key, (0, 0.0))
        self._timers[key] = (count + 1, total_seconds + value)

    def counter_samples(self) -> tuple[CounterSample, ...]:
        """返回按指标名和标签排序的计数器样本。"""
        return tuple(
            CounterSample(name=name, labels=labels, value=value)
            for (name, labels), value in sorted(self._counters.items())
        )

    def timer_samples(self) -> tuple[TimerSample, ...]:
        """返回按指标名和标签排序的耗时样本。"""
        return tuple(
            TimerSample(
                name=name,
                labels=labels,
                count=count,
                total_seconds=total_seconds,
            )
            for (name, labels), (count, total_seconds) in sorted(self._timers.items())
        )


def _label_key(labels: Mapping[str, str]) -> LabelKey:
    return tuple(sorted(labels.items()))


def _ensure_metric_name(name: str, known_names: frozenset[str]) -> None:
    if name not in known_names:
        raise ValueError(f"未知 DataSentry 自监控指标：{name}")
