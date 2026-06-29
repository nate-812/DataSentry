import pytest

from datasentry.errors import DataSentryError
from datasentry.runbooks import BuiltInRunbookCatalog, render_idempotency_key, render_lock_key


def test_render_idempotency_key_is_stable() -> None:
    runbook = BuiltInRunbookCatalog().get("mock.restart_preview")

    key = render_idempotency_key(
        runbook,
        parameters={"reason": "演练", "target": "api"},
        incident_id=None,
    )

    assert key == "mock.restart_preview:1.0.0:api:none"


def test_render_lock_key_uses_target() -> None:
    runbook = BuiltInRunbookCatalog().get("mock.restart_preview")

    assert render_lock_key(runbook, {"target": "api"}) == "runbook:mock.restart_preview:api"


@pytest.mark.parametrize("target", ["", "   ", ["api"], {"name": "api"}, True])
def test_render_key_rejects_invalid_target(target: object) -> None:
    runbook = BuiltInRunbookCatalog().get("mock.restart_preview")

    with pytest.raises(DataSentryError) as error:
        render_lock_key(runbook, {"target": target})

    assert error.value.code == "runbook.invalid_parameters"
    assert error.value.details == {"parameter": "target"}


def test_render_template_reports_missing_placeholder() -> None:
    runbook = (
        BuiltInRunbookCatalog()
        .get("mock.restart_preview")
        .model_copy(update={"lock_key_template": "runbook:{name}:{scope}"})
    )

    with pytest.raises(DataSentryError) as error:
        render_lock_key(runbook, {"target": "api"})

    assert error.value.code == "runbook.invalid_template"
    assert error.value.details == {"placeholder": "scope"}
