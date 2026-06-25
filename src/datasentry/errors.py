"""可安全暴露到进程边界的稳定应用异常。"""

from collections.abc import Mapping


class DataSentryError(Exception):
    """DataSentry 预期异常的基类。"""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})

    def to_dict(self) -> dict[str, object]:
        """返回稳定且可安全展示给用户的异常数据。"""
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


class ConfigurationError(DataSentryError):
    """运行时配置无效时抛出。"""


class StorageError(DataSentryError):
    """持久化操作无法安全完成时抛出。"""


class NotFoundError(DataSentryError):
    """请求的领域对象不存在时抛出。"""
