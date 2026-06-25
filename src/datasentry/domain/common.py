"""Shared primitives for immutable domain models."""

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict


class DomainModel(BaseModel):
    """Strict immutable base model used across the domain."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


def new_id() -> str:
    """Return a new application-generated UUID."""
    return str(uuid4())


def utc_now() -> datetime:
    """Return the current UTC time."""
    return datetime.now(UTC)


def require_aware_datetime(value: datetime) -> datetime:
    """Normalize an aware datetime to UTC and reject naive values."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include timezone information")
    return value.astimezone(UTC)


def normalize_optional_datetime(value: datetime | None) -> datetime | None:
    """Normalize an optional aware datetime while preserving None."""
    if value is None:
        return None
    return require_aware_datetime(value)
