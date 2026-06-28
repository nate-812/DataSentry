from datetime import UTC, datetime

from datasentry.domain import Evidence, EvidenceStatus, Finding, Severity
from datasentry.llm import (
    AnswerContext,
    AnswerSummarizer,
    DisabledLLMProvider,
    LLMMessage,
    LLMOptions,
    LLMProviderError,
    LLMProviderName,
    LLMResult,
    LLMStatus,
    MockLLMProvider,
)

NOW = datetime(2026, 6, 27, 8, 0, tzinfo=UTC)


def _finding() -> Finding:
    return Finding(
        inspection_id="11111111-1111-4111-8111-111111111111",
        severity=Severity.WARNING,
        status=EvidenceStatus.CONFIRMED,
        claim="Kline 数据在 Flink 之后停止推进",
        evidence=[
            Evidence(
                claim="Flink Kline Job 已完成只读检查",
                status=EvidenceStatus.CONFIRMED,
                source="inspection",
                target="flink",
                observed_at=NOW,
                summary="Checkpoint 正常但 Doris 新鲜度滞后",
            )
        ],
        impact="前端可能看到旧数据",
        recommendation="检查 Flink Kline Job 和 Doris 新鲜度",
        unknowns=["Spring API 返回空数组的原因仍需确认"],
        created_at=NOW,
    )


class CapturingProvider:
    def __init__(self, result: LLMResult) -> None:
        self.messages: list[LLMMessage] = []
        self.options: LLMOptions | None = None
        self._result = result

    def generate(self, messages: list[LLMMessage], options: LLMOptions) -> LLMResult:
        self.messages = messages
        self.options = options
        return self._result


class FailingProvider:
    def generate(self, messages: list[LLMMessage], options: LLMOptions) -> LLMResult:
        del messages, options
        raise LLMProviderError(
            code="llm.upstream_error",
            message="secret-key 泄露风险",
        )


def test_summarizer_uses_deterministic_template_when_llm_disabled() -> None:
    summarizer = AnswerSummarizer(provider=DisabledLLMProvider())

    summary = summarizer.summarize(
        AnswerContext(
            question="为什么K线不更新",
            findings=[_finding()],
            tool_invocation_count=3,
        )
    )

    assert summary.llm_status == "disabled"
    assert "当前结论" in summary.content
    assert "Kline 数据在 Flink 之后停止推进" in summary.content


def test_summarizer_uses_model_content_when_available() -> None:
    summarizer = AnswerSummarizer(provider=MockLLMProvider(content="模型整理后的回答"))

    summary = summarizer.summarize(
        AnswerContext(
            question="为什么K线不更新",
            findings=[_finding()],
            tool_invocation_count=3,
        )
    )

    assert summary.llm_status == "available"
    assert summary.content == "模型整理后的回答"


def test_summarizer_falls_back_when_provider_raises() -> None:
    summarizer = AnswerSummarizer(provider=FailingProvider())

    summary = summarizer.summarize(
        AnswerContext(
            question="为什么K线不更新",
            findings=[_finding()],
            tool_invocation_count=3,
        )
    )

    assert summary.llm_status == "unavailable"
    assert "当前结论" in summary.content
    assert "Kline 数据在 Flink 之后停止推进" in summary.content
    assert "secret-key" not in summary.content


def test_summarizer_reports_insufficient_evidence_without_findings() -> None:
    summarizer = AnswerSummarizer(provider=DisabledLLMProvider())

    summary = summarizer.summarize(
        AnswerContext(
            question="为什么K线不更新",
            findings=[],
            tool_invocation_count=0,
        )
    )

    assert summary.llm_status == "disabled"
    assert "证据不足" in summary.content
    assert "继续收集现场证据" in summary.content


def test_summarizer_prompt_contains_safety_rules_and_context() -> None:
    provider = CapturingProvider(
        LLMResult(
            provider=LLMProviderName.MOCK,
            status=LLMStatus.AVAILABLE,
            content="模型回答",
        )
    )
    summarizer = AnswerSummarizer(provider=provider)

    summarizer.summarize(
        AnswerContext(
            question="为什么K线不更新",
            findings=[_finding()],
            tool_invocation_count=3,
        )
    )

    system_prompt = provider.messages[0].content
    user_prompt = provider.messages[1].content
    assert "只能基于给定证据回答" in system_prompt
    assert "不得编造事实" in system_prompt
    assert "不得生成 Shell、SQL 或 Redis 写命令" in system_prompt
    assert "为什么K线不更新" in user_prompt
    assert "Kline 数据在 Flink 之后停止推进" in user_prompt
    assert "已完成 3 次只读工具调用" in user_prompt
