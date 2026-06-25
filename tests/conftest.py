from datetime import UTC, datetime

import pytest


@pytest.fixture
def observed_at() -> datetime:
    return datetime(2026, 6, 25, 12, 0, tzinfo=UTC)


@pytest.fixture
def inspection_id() -> str:
    return "11111111-1111-4111-8111-111111111111"
