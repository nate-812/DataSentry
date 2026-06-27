from datasentry.observability import MetricRegistry, render_prometheus_text


def test_metric_registry_renders_counters_and_histogram_sum() -> None:
    registry = MetricRegistry()

    registry.increment(
        "datasentry_tool_invocations_total",
        {"tool": "flink.jobs", "status": "success"},
    )
    registry.increment(
        "datasentry_tool_failures_total",
        {"tool": "redis.sample", "error": "timeout"},
    )
    registry.observe_seconds(
        "datasentry_notification_format_seconds",
        0.125,
        {"channel": "wecom"},
    )

    text = render_prometheus_text(registry)

    assert "# TYPE datasentry_tool_invocations_total counter" in text
    assert 'datasentry_tool_invocations_total{status="success",tool="flink.jobs"} 1' in text
    assert 'datasentry_tool_failures_total{error="timeout",tool="redis.sample"} 1' in text
    assert 'datasentry_notification_format_seconds_count{channel="wecom"} 1' in text
    assert 'datasentry_notification_format_seconds_sum{channel="wecom"} 0.125' in text


def test_metric_registry_rejects_unknown_metric_name() -> None:
    registry = MetricRegistry()

    try:
        registry.increment("unknown_total", {})
    except ValueError as error:
        assert str(error) == "未知 DataSentry 自监控指标：unknown_total"
    else:
        raise AssertionError("expected ValueError")
