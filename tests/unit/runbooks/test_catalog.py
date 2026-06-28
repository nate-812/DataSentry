import pytest

from datasentry.domain import OperationRisk
from datasentry.errors import NotFoundError
from datasentry.runbooks import BuiltInRunbookCatalog, ExecutionMode


def test_builtin_catalog_lists_mock_runbooks_and_forbidden_guard() -> None:
    catalog = BuiltInRunbookCatalog()

    runbooks = catalog.list_runbooks()

    assert [item.name for item in runbooks] == [
        "mock.restart_preview",
        "mock.clear_cache_preview",
        "forbidden.shell_command",
    ]
    assert runbooks[0].risk is OperationRisk.L1
    assert runbooks[0].execution_mode is ExecutionMode.MOCK
    assert runbooks[2].risk is OperationRisk.FORBIDDEN
    assert runbooks[2].execution_mode is ExecutionMode.FORBIDDEN


def test_builtin_catalog_returns_copy_by_name() -> None:
    catalog = BuiltInRunbookCatalog()

    runbook = catalog.get("mock.restart_preview")

    assert runbook.name == "mock.restart_preview"
    assert runbook.parameter_schema["required"] == ["target", "reason"]
    assert runbook.enabled is True


def test_builtin_catalog_rejects_unknown_runbook() -> None:
    catalog = BuiltInRunbookCatalog()

    with pytest.raises(NotFoundError, match="未找到指定 Runbook"):
        catalog.get("missing.runbook")
