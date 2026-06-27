import json

import httpx
import pytest

from datasentry.llm import (
    DisabledLLMProvider,
    LLMMessage,
    LLMOptions,
    LLMProviderError,
    LLMProviderName,
    MockLLMProvider,
    OpenAICompatibleProvider,
)


def test_disabled_provider_reports_disabled_without_network() -> None:
    provider = DisabledLLMProvider()

    result = provider.generate([LLMMessage(role="user", content="hello")], LLMOptions())

    assert result.provider == LLMProviderName.DISABLED
    assert result.status == "disabled"
    assert result.content == ""


def test_mock_provider_returns_stable_text() -> None:
    provider = MockLLMProvider(content="模拟摘要")

    result = provider.generate([LLMMessage(role="user", content="hello")], LLMOptions())

    assert result.provider == LLMProviderName.MOCK
    assert result.status == "available"
    assert result.content == "模拟摘要"


def test_openai_compatible_provider_sends_authorization_header_and_payload() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "模型摘要"}}]},
        )

    provider = OpenAICompatibleProvider(
        base_url="https://llm.example.test/v1/",
        api_key="secret-key",
        model="ops-model",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = provider.generate(
        [LLMMessage(role="user", content="hello")],
        LLMOptions(temperature=0.1, max_tokens=128),
    )

    payload = json.loads(requests[0].content)
    assert result.content == "模型摘要"
    assert requests[0].method == "POST"
    assert str(requests[0].url) == "https://llm.example.test/v1/chat/completions"
    assert requests[0].headers["authorization"] == "Bearer secret-key"
    assert payload == {
        "model": "ops-model",
        "messages": [{"role": "user", "content": "hello"}],
        "temperature": 0.1,
        "max_tokens": 128,
    }


def test_openai_compatible_provider_redacts_api_key_in_authentication_errors() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "secret-key rejected"}})

    provider = OpenAICompatibleProvider(
        base_url="https://llm.example.test/v1",
        api_key="secret-key",
        model="ops-model",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(LLMProviderError) as raised:
        provider.generate([LLMMessage(role="user", content="hello")], LLMOptions())

    assert raised.value.code == "llm.authentication_failed"
    assert "secret-key" not in raised.value.message


def test_openai_compatible_provider_maps_timeout_without_leaking_key() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("secret-key timed out")

    provider = OpenAICompatibleProvider(
        base_url="https://llm.example.test/v1",
        api_key="secret-key",
        model="ops-model",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(LLMProviderError) as raised:
        provider.generate([LLMMessage(role="user", content="hello")], LLMOptions())

    assert raised.value.code == "llm.timeout"
    assert "secret-key" not in raised.value.message
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None


def test_openai_compatible_provider_maps_http_error_without_leaking_key() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("secret-key connection failed")

    provider = OpenAICompatibleProvider(
        base_url="https://llm.example.test/v1",
        api_key="secret-key",
        model="ops-model",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(LLMProviderError) as raised:
        provider.generate([LLMMessage(role="user", content="hello")], LLMOptions())

    assert raised.value.code == "llm.upstream_error"
    assert "secret-key" not in raised.value.message
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None


def test_openai_compatible_provider_maps_non_success_status_without_leaking_body() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="upstream failed with secret-key")

    provider = OpenAICompatibleProvider(
        base_url="https://llm.example.test/v1",
        api_key="secret-key",
        model="ops-model",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(LLMProviderError) as raised:
        provider.generate([LLMMessage(role="user", content="hello")], LLMOptions())

    assert raised.value.code == "llm.upstream_error"
    assert "secret-key" not in raised.value.message
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None


def test_openai_compatible_provider_fails_safely_when_content_is_missing() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {}}]})

    provider = OpenAICompatibleProvider(
        base_url="https://llm.example.test/v1",
        api_key="secret-key",
        model="ops-model",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(LLMProviderError) as raised:
        provider.generate([LLMMessage(role="user", content="hello")], LLMOptions())

    assert raised.value.code == "llm.upstream_error"
    assert "secret-key" not in raised.value.message
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
