"""白名单工具执行期间可安全暴露的稳定异常。"""

from datasentry.errors import DataSentryError


class ToolError(DataSentryError):
    """单个只读工具调用失败。"""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        retryable: bool = False,
    ) -> None:
        super().__init__(
            code=code,
            message=message,
            details={"retryable": retryable},
        )
        self.retryable = retryable
