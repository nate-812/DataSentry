"""内置有限自治策略目录。"""

from datasentry.autonomy.models import AutonomyPolicy
from datasentry.errors import NotFoundError


class BuiltInAutonomyPolicyCatalog:
    """提供首批本地 mock Runbook 的默认自治策略。"""

    def __init__(self) -> None:
        self._policies = {
            "mock.restart_preview": AutonomyPolicy(runbook_name="mock.restart_preview"),
            "mock.clear_cache_preview": AutonomyPolicy(
                runbook_name="mock.clear_cache_preview",
            ),
        }

    def list_policies(self) -> list[AutonomyPolicy]:
        return [policy.model_copy(deep=True) for policy in self._policies.values()]

    def get(self, runbook_name: str) -> AutonomyPolicy:
        policy = self._policies.get(runbook_name)
        if policy is None:
            raise NotFoundError(
                code="autonomy_policy.not_found",
                message="未找到指定自治策略",
                details={"runbook_name": runbook_name},
            )
        return policy.model_copy(deep=True)
