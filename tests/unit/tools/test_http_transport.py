import httpx
import pytest

from datasentry.tools.errors import ToolError
from datasentry.tools.targets import HttpTarget, ToolLimits
from datasentry.tools.transports.http import HttpTransport


def test_http_transport_gets_json_from_fixed_base_url() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert str(request.url) == "http://flink.test/jobs/overview"
        return httpx.Response(200, json={"jobs": []})

    transport = HttpTransport(
        targets={"flink": HttpTarget(base_url="http://flink.test")},
        limits=ToolLimits(),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert transport.get_json("flink", "/jobs/overview") == {"jobs": []}


def test_http_transport_rejects_absolute_or_cross_host_path() -> None:
    transport = HttpTransport(
        targets={"flink": HttpTarget(base_url="http://flink.test")},
        limits=ToolLimits(),
        client=httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200))),
    )

    with pytest.raises(ToolError) as raised:
        transport.get_json("flink", "http://evil.test/jobs")

    assert raised.value.code == "tool.invalid_arguments"


def test_http_transport_rejects_oversized_response() -> None:
    transport = HttpTransport(
        targets={"flink": HttpTarget(base_url="http://flink.test")},
        limits=ToolLimits(max_output_bytes=1024),
        client=httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"x" * 1025))
        ),
    )

    with pytest.raises(ToolError) as raised:
        transport.get_json("flink", "/overview")

    assert raised.value.code == "tool.output_limit_exceeded"


def test_http_transport_retries_one_transient_response() -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"status": "ok"})

    transport = HttpTransport(
        targets={"api": HttpTarget(base_url="http://api.test")},
        limits=ToolLimits(retry_attempts=1),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert transport.get_json("api", "/health") == {"status": "ok"}
    assert attempts == 2


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (httpx.Response(302, headers={"location": "http://evil.test"}), "tool.policy_denied"),
        (httpx.Response(401), "tool.authentication_failed"),
        (httpx.Response(500), "tool.upstream_error"),
        (httpx.Response(200, content=b"not-json"), "tool.parse_failed"),
    ],
)
def test_http_transport_maps_unsafe_or_invalid_responses(
    response: httpx.Response,
    code: str,
) -> None:
    transport = HttpTransport(
        targets={"api": HttpTarget(base_url="http://api.test")},
        limits=ToolLimits(retry_attempts=0),
        client=httpx.Client(transport=httpx.MockTransport(lambda _: response)),
    )

    with pytest.raises(ToolError) as raised:
        transport.get_json("api", "/health")

    assert raised.value.code == code


@pytest.mark.parametrize(
    ("exception", "code"),
    [
        (httpx.ReadTimeout("timeout"), "tool.timeout"),
        (httpx.ConnectError("failed"), "tool.connection_failed"),
    ],
)
def test_http_transport_maps_transport_errors(
    exception: httpx.HTTPError,
    code: str,
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise exception

    transport = HttpTransport(
        targets={"api": HttpTarget(base_url="http://api.test")},
        limits=ToolLimits(retry_attempts=0),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ToolError) as raised:
        transport.get_json("api", "/health")

    assert raised.value.code == code


def test_http_transport_rejects_unknown_target() -> None:
    transport = HttpTransport(targets={}, limits=ToolLimits())

    with pytest.raises(ToolError) as raised:
        transport.get_json("missing", "/health")

    assert raised.value.code == "tool.configuration"
