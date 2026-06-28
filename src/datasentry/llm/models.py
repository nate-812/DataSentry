"""LLM Provider 的稳定输入输出模型。"""

from enum import StrEnum

from pydantic import Field

from datasentry.domain.common import DomainModel


class LLMProviderName(StrEnum):
    DISABLED = "disabled"
    MOCK = "mock"
    OPENAI_COMPATIBLE = "openai_compatible"


class LLMStatus(StrEnum):
    DISABLED = "disabled"
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class LLMMessage(DomainModel):
    role: str = Field(min_length=1)
    content: str = Field(min_length=1)


class LLMOptions(DomainModel):
    temperature: float = 0.2
    max_tokens: int = 800


class LLMResult(DomainModel):
    provider: LLMProviderName
    status: LLMStatus
    content: str
