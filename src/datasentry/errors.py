"""Stable application errors safe to expose at process boundaries."""

from collections.abc import Mapping


class DataSentryError(Exception):
    """Base class for expected DataSentry failures."""

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
        """Return the stable, user-safe error payload."""
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


class ConfigurationError(DataSentryError):
    """Raised when runtime configuration is invalid."""


class StorageError(DataSentryError):
    """Raised when persistence cannot complete safely."""


class NotFoundError(DataSentryError):
    """Raised when a requested domain object does not exist."""
