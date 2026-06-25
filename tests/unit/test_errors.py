from datasentry.errors import DataSentryError


def test_datasentry_error_exposes_stable_safe_payload() -> None:
    error = DataSentryError(
        code="storage.unavailable",
        message="数据库当前不可用",
        details={"database": "local"},
    )

    assert error.to_dict() == {
        "code": "storage.unavailable",
        "message": "数据库当前不可用",
        "details": {"database": "local"},
    }
