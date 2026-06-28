"""内置 Runbook 目录。"""

from datasentry.domain.enums import OperationRisk
from datasentry.errors import NotFoundError
from datasentry.runbooks.models import ExecutionMode, Runbook


def _mock_runbook(name: str, title: str, description: str) -> Runbook:
    return Runbook(
        name=name,
        version="1.0.0",
        title=title,
        description=description,
        risk=OperationRisk.L1,
        execution_mode=ExecutionMode.MOCK,
        parameter_schema={
            "type": "object",
            "required": ["target", "reason"],
            "properties": {
                "target": {"type": "string"},
                "reason": {"type": "string"},
                "incident_id": {"type": "string"},
            },
        },
        precheck={"summary": "确认目标存在且当前状态可读"},
        postcheck={"summary": "确认模拟操作后目标状态仍可读"},
        lock_key_template="runbook:{name}:{target}",
        idempotency_key_template="{name}:{version}:{target}:{incident_id}",
    )


class BuiltInRunbookCatalog:
    def __init__(self) -> None:
        self._runbooks = (
            _mock_runbook(
                "mock.restart_preview",
                "模拟重启预演",
                "仅用于本地审批与执行链路演练，不触碰生产服务。",
            ),
            _mock_runbook(
                "mock.clear_cache_preview",
                "模拟清理缓存预演",
                "仅用于本地审批与执行链路演练，不清理真实缓存。",
            ),
            Runbook(
                name="forbidden.shell_command",
                version="1.0.0",
                title="禁止任意 Shell",
                description="任意 Shell 不属于第一版 Runbook 范围。",
                risk=OperationRisk.FORBIDDEN,
                execution_mode=ExecutionMode.FORBIDDEN,
                parameter_schema={"type": "object"},
                precheck={"summary": "策略固定拒绝任意 Shell"},
                postcheck={"summary": "无执行动作，无需验证"},
                lock_key_template="runbook:{name}:{target}",
                idempotency_key_template="{name}:{version}:{target}:{incident_id}",
                enabled=False,
                audit_notes="任意 Shell 明确禁止，保留目录项用于策略防护测试。",
            ),
        )
        self._runbooks_by_name = {runbook.name: runbook for runbook in self._runbooks}

    def list_runbooks(self) -> list[Runbook]:
        """按稳定顺序返回内置 Runbook 副本。"""
        return [runbook.model_copy(deep=True) for runbook in self._runbooks]

    def get(self, name: str) -> Runbook:
        """按名称读取 Runbook 副本。"""
        runbook = self._runbooks_by_name.get(name)
        if runbook is None:
            raise NotFoundError(
                code="runbook.not_found",
                message="未找到指定 Runbook",
                details={"runbook_name": name},
            )
        return runbook.model_copy(deep=True)
