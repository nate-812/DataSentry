"""不可变领域模型使用的共享基础能力。"""

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict


class DomainModel(BaseModel):
    """领域层统一使用的严格不可变基础模型。"""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


def new_id() -> str:
    """返回由应用生成的新 UUID。"""
    return str(uuid4())


def utc_now() -> datetime:
    """返回当前 UTC 时间。"""
    return datetime.now(UTC)


def require_aware_datetime(value: datetime) -> datetime:
    """将带时区的 datetime 统一转换为 UTC，并拒绝无时区值。"""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime 必须包含时区信息")
    return value.astimezone(UTC)


def normalize_optional_datetime(value: datetime | None) -> datetime | None:
    """转换可选的带时区 datetime，并保留 None。"""
    if value is None:
        return None
    return require_aware_datetime(value)
