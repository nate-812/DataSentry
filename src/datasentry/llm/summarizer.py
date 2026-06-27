"""将确定性诊断结果整理成面向用户的中文回答。"""

from pydantic import Field

from datasentry.domain import Finding
from datasentry.domain.common import DomainModel
from datasentry.llm.models import LLMMessage, LLMOptions
from datasentry.llm.providers import LLMProvider, LLMProviderError

SYSTEM_PROMPT = (
    "你是 DataSentry 运维 Agent。只能基于给定证据回答，"
    "不得编造事实，不得生成 Shell、SQL 或 Redis 写命令。"
)


class AnswerContext(DomainModel):
    question: str = Field(min_length=1)
    findings: list[Finding] = Field(default_factory=list)
    tool_invocation_count: int = Field(default=0, ge=0)


class AnswerSummary(DomainModel):
    content: str = Field(min_length=1)
    llm_status: str = Field(min_length=1)


class AnswerSummarizer:
    """将证据化诊断上下文交给 LLM，并保留确定性降级回答。"""

    def __init__(self, *, provider: LLMProvider) -> None:
        self._provider = provider

    def summarize(self, context: AnswerContext) -> AnswerSummary:
        deterministic = self._deterministic_summary(context)
        try:
            result = self._provider.generate(
                [
                    LLMMessage(role="system", content=SYSTEM_PROMPT),
                    LLMMessage(role="user", content=deterministic),
                ],
                LLMOptions(),
            )
        except LLMProviderError:
            return AnswerSummary(content=deterministic, llm_status="unavailable")
        if result.status == "available" and result.content.strip():
            return AnswerSummary(
                content=result.content.strip(),
                llm_status=result.status.value,
            )
        return AnswerSummary(content=deterministic, llm_status=result.status.value)

    @staticmethod
    def _deterministic_summary(context: AnswerContext) -> str:
        if not context.findings:
            return (
                f"用户问题：{context.question}\n"
                "当前结论：证据不足，尚不能确认根因。\n"
                f"已确认事实：已完成 {context.tool_invocation_count} 次只读工具调用。\n"
                "推断：暂无。\n"
                "未知项：缺少可判定的 Finding。\n"
                "建议下一步：继续收集现场证据。"
            )

        finding = context.findings[0]
        unknowns = "、".join(finding.unknowns) if finding.unknowns else "暂无"
        evidence_summaries = "、".join(evidence.summary for evidence in finding.evidence)
        return (
            f"用户问题：{context.question}\n"
            f"当前结论：{finding.claim}\n"
            f"已确认事实：已完成 {context.tool_invocation_count} 次只读工具调用。"
            f"{evidence_summaries}\n"
            f"推断：{finding.impact}\n"
            f"未知项：{unknowns}\n"
            f"建议下一步：{finding.recommendation}"
        )
