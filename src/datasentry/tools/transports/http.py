"""只允许固定目标 GET 请求的同步 HTTP 传输。"""

from collections.abc import Mapping

import httpx
from pydantic import JsonValue, TypeAdapter, ValidationError

from datasentry.tools.errors import ToolError
from datasentry.tools.targets import HttpTarget, ToolLimits

JSON_ADAPTER: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)
TRANSIENT_STATUSES = frozenset({429, 502, 503, 504})


class HttpTransport:
    """对固定 base URL 执行有限重试和输出限制的 GET。"""

    def __init__(
        self,
        *,
        targets: Mapping[str, HttpTarget],
        limits: ToolLimits,
        client: httpx.Client | None = None,
    ) -> None:
        self._targets = dict(targets)
        self._limits = limits
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(
                connect=limits.connect_timeout_seconds,
                read=limits.read_timeout_seconds,
                write=limits.read_timeout_seconds,
                pool=limits.connect_timeout_seconds,
            ),
            follow_redirects=False,
        )

    def get_json(self, target: str, path: str) -> JsonValue:
        """从已配置目标读取受限 JSON。"""
        configured = self._targets.get(target)
        if configured is None:
            raise ToolError(
                code="tool.configuration",
                message="HTTP 目标未配置",
            )
        if not path.startswith("/") or path.startswith("//") or "://" in path:
            raise ToolError(
                code="tool.invalid_arguments",
                message="HTTP 路径必须是固定相对路径",
            )
        url = f"{configured.base_url}{path}"
        attempts = self._limits.retry_attempts + 1
        for attempt in range(attempts):
            try:
                response = self._client.get(url)
            except httpx.TimeoutException as error:
                if attempt + 1 < attempts:
                    continue
                raise ToolError(
                    code="tool.timeout",
                    message="HTTP 目标读取超时",
                    retryable=True,
                ) from error
            except httpx.HTTPError as error:
                if attempt + 1 < attempts:
                    continue
                raise ToolError(
                    code="tool.connection_failed",
                    message="HTTP 目标连接失败",
                    retryable=True,
                ) from error
            if response.status_code in TRANSIENT_STATUSES and attempt + 1 < attempts:
                continue
            if response.is_redirect:
                raise ToolError(
                    code="tool.policy_denied",
                    message="HTTP 工具拒绝重定向",
                )
            if response.status_code in {401, 403}:
                raise ToolError(
                    code="tool.authentication_failed",
                    message="HTTP 目标认证失败",
                )
            if response.status_code >= 400:
                raise ToolError(
                    code="tool.upstream_error",
                    message="HTTP 目标返回错误状态",
                    retryable=response.status_code in TRANSIENT_STATUSES,
                )
            if len(response.content) > self._limits.max_output_bytes:
                raise ToolError(
                    code="tool.output_limit_exceeded",
                    message="HTTP 响应超过输出上限",
                )
            try:
                return JSON_ADAPTER.validate_python(response.json())
            except (ValueError, ValidationError) as error:
                raise ToolError(
                    code="tool.parse_failed",
                    message="HTTP 响应不是有效 JSON",
                ) from error
        raise ToolError(
            code="tool.internal_error",
            message="HTTP 重试状态异常",
        )
