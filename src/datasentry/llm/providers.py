"""可插拔 LLM Provider。"""

from typing import Protocol

import httpx

from datasentry.errors import DataSentryError
from datasentry.llm.models import LLMMessage, LLMOptions, LLMProviderName, LLMResult, LLMStatus


class LLMProviderError(DataSentryError):
    """LLM 调用失败，错误信息已脱敏。"""


class LLMProvider(Protocol):
    def generate(self, messages: list[LLMMessage], options: LLMOptions) -> LLMResult:
        raise NotImplementedError  # pragma: no cover


class DisabledLLMProvider:
    def generate(self, messages: list[LLMMessage], options: LLMOptions) -> LLMResult:
        del messages, options
        return LLMResult(
            provider=LLMProviderName.DISABLED,
            status=LLMStatus.DISABLED,
            content="",
        )


class MockLLMProvider:
    def __init__(self, content: str = "这是模拟 LLM 摘要。") -> None:
        self._content = content

    def generate(self, messages: list[LLMMessage], options: LLMOptions) -> LLMResult:
        del messages, options
        return LLMResult(
            provider=LLMProviderName.MOCK,
            status=LLMStatus.AVAILABLE,
            content=self._content,
        )


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        client: httpx.Client | None = None,
        timeout_seconds: float = 20,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def generate(self, messages: list[LLMMessage], options: LLMOptions) -> LLMResult:
        payload = {
            "model": self._model,
            "messages": [message.model_dump(mode="json") for message in messages],
            "temperature": options.temperature,
            "max_tokens": options.max_tokens,
        }
        try:
            response = self._client.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
            )
        except httpx.TimeoutException as error:
            raise LLMProviderError(
                code="llm.timeout",
                message="LLM 调用超时",
            ) from error
        except httpx.HTTPError as error:
            raise LLMProviderError(
                code="llm.upstream_error",
                message="LLM 上游调用失败",
            ) from error
        self._raise_for_status(response)
        return LLMResult(
            provider=LLMProviderName.OPENAI_COMPATIBLE,
            status=LLMStatus.AVAILABLE,
            content=self._extract_content(response),
        )

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code in {401, 403}:
            raise LLMProviderError(
                code="llm.authentication_failed",
                message="LLM 认证失败",
                details={"status_code": response.status_code},
            )
        if not response.is_success:
            raise LLMProviderError(
                code="llm.upstream_error",
                message="LLM 上游返回错误状态",
                details={"status_code": response.status_code},
            )

    @staticmethod
    def _extract_content(response: httpx.Response) -> str:
        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise LLMProviderError(
                code="llm.upstream_error",
                message="LLM 上游响应缺少有效内容",
            ) from error
        if not isinstance(content, str):
            raise LLMProviderError(
                code="llm.upstream_error",
                message="LLM 上游响应缺少有效内容",
            )
        return content
