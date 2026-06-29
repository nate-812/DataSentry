"""Runbook 幂等键与并发锁键渲染。"""

from pydantic import JsonValue

from datasentry.errors import DataSentryError
from datasentry.runbooks.models import Runbook


def render_idempotency_key(
    runbook: Runbook,
    parameters: dict[str, JsonValue],
    incident_id: str | None,
) -> str:
    context = _render_context(runbook, parameters, incident_id)
    return _render_template(runbook.idempotency_key_template, context)


def render_lock_key(runbook: Runbook, parameters: dict[str, JsonValue]) -> str:
    context = _render_context(runbook, parameters, incident_id=None)
    return _render_template(runbook.lock_key_template, context)


def _render_context(
    runbook: Runbook,
    parameters: dict[str, JsonValue],
    incident_id: str | None,
) -> dict[str, str]:
    target = require_target(parameters)
    return {
        "name": runbook.name,
        "version": runbook.version,
        "target": target,
        "incident_id": incident_id or "none",
    }


def require_target(parameters: dict[str, JsonValue]) -> str:
    target = parameters.get("target")
    if not isinstance(target, str) or not target.strip():
        raise DataSentryError(
            code="runbook.invalid_parameters",
            message="Runbook 参数缺少 target",
            details={"parameter": "target"},
        )
    return target.strip()


def _render_template(template: str, context: dict[str, str]) -> str:
    try:
        return template.format(**context)
    except KeyError as error:
        placeholder = str(error).strip("'")
        raise DataSentryError(
            code="runbook.invalid_template",
            message="Runbook 模板包含不支持的占位符",
            details={"placeholder": placeholder},
        ) from error
