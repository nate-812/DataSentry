import pytest

from datasentry.errors import DataSentryError
from datasentry.runbooks import BuiltInRunbookCatalog, RunbookPolicy


def test_policy_allows_enabled_mock_l1_runbook() -> None:
    runbook = BuiltInRunbookCatalog().get("mock.restart_preview")

    RunbookPolicy().assert_request_allowed(runbook)


def test_policy_rejects_forbidden_runbook() -> None:
    runbook = BuiltInRunbookCatalog().get("forbidden.shell_command")

    with pytest.raises(DataSentryError) as error:
        RunbookPolicy().assert_request_allowed(runbook)

    assert error.value.code == "runbook.forbidden"
