"""Prometheus 文本格式导出。"""

from datasentry.observability.metrics import MetricRegistry


def render_prometheus_text(registry: MetricRegistry) -> str:
    """将自监控指标渲染为 Prometheus text exposition 格式。"""
    lines: list[str] = []
    emitted_types: set[str] = set()
    for counter_sample in registry.counter_samples():
        if counter_sample.name not in emitted_types:
            lines.append(f"# TYPE {counter_sample.name} counter")
            emitted_types.add(counter_sample.name)
        lines.append(
            f"{counter_sample.name}{_render_labels(counter_sample.labels)} "
            f"{_format_number(counter_sample.value)}"
        )
    for timer_sample in registry.timer_samples():
        if timer_sample.name not in emitted_types:
            lines.append(f"# TYPE {timer_sample.name} summary")
            emitted_types.add(timer_sample.name)
        labels = _render_labels(timer_sample.labels)
        lines.append(f"{timer_sample.name}_count{labels} {timer_sample.count}")
        lines.append(
            f"{timer_sample.name}_sum{labels} {_format_number(timer_sample.total_seconds)}"
        )
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def _render_labels(labels: tuple[tuple[str, str], ...]) -> str:
    if not labels:
        return ""
    rendered = ",".join(f'{key}="{_escape_label_value(value)}"' for key, value in labels)
    return f"{{{rendered}}}"


def _escape_label_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _format_number(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return str(value)
