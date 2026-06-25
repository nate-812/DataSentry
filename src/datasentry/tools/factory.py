"""生产只读工具和真实巡检服务的固定依赖装配。"""

from pathlib import Path

from datasentry.diagnosis import (
    ComponentDownRule,
    ConfigurationMismatchRule,
    DiagnosisService,
    FlinkBackpressureRule,
    KlineStalledAtFlinkRule,
)
from datasentry.knowledge import KnowledgeIndex, KnowledgeRouter, build_streamlake_lineage
from datasentry.storage import Repository
from datasentry.tools.adapters import (
    ApiHealthTool,
    DorisFreshnessTool,
    FlinkBackpressureTool,
    FlinkCheckpointsTool,
    FlinkJobsTool,
    FlinkJobTool,
    HostStatusTool,
    KafkaGroupTool,
    KafkaTopicsTool,
    KafkaTopicTool,
    MySqlTableSampleTool,
    RecentLogsTool,
    RedisKeySampleTool,
    ServiceStatusTool,
)
from datasentry.tools.collector import InspectionCollector
from datasentry.tools.gateway import ToolGateway
from datasentry.tools.planner import ReadOnlyInspectionPlanner
from datasentry.tools.service import LiveInspectionService
from datasentry.tools.targets import (
    EnvironmentSecretResolver,
    TargetCatalog,
)
from datasentry.tools.transports import (
    HttpTransport,
    MySqlTransport,
    RedisTransport,
    SshTransport,
)


def build_live_inspection_service(
    *,
    repository: Repository,
    targets: TargetCatalog,
    knowledge_root: Path,
) -> LiveInspectionService:
    """构造固定工具注册表和真实只读巡检服务。"""
    secrets = EnvironmentSecretResolver()
    http = HttpTransport(targets=targets.http, limits=targets.limits)
    ssh = SshTransport(
        hosts=targets.hosts,
        targets=targets.ssh,
        limits=targets.limits,
        secrets=secrets,
    )
    mysql = MySqlTransport(
        hosts=targets.hosts,
        targets=targets.mysql,
        limits=targets.limits,
        secrets=secrets,
    )
    redis = RedisTransport(
        hosts=targets.hosts,
        targets=targets.redis,
        limits=targets.limits,
        secrets=secrets,
    )
    tools = (
        FlinkJobsTool(http),
        FlinkJobTool(http),
        FlinkCheckpointsTool(http),
        FlinkBackpressureTool(http),
        ApiHealthTool(http),
        HostStatusTool(ssh),
        ServiceStatusTool(ssh),
        KafkaTopicsTool(ssh),
        KafkaTopicTool(ssh),
        KafkaGroupTool(ssh),
        DorisFreshnessTool(mysql),
        RedisKeySampleTool(redis),
        MySqlTableSampleTool(mysql),
        RecentLogsTool(ssh, sources=targets.logs),
    )
    knowledge = KnowledgeIndex.load(knowledge_root)
    diagnosis = DiagnosisService(
        repository=repository,
        knowledge_index=knowledge,
        router=KnowledgeRouter(knowledge),
        lineage_graph=build_streamlake_lineage(),
        rules=(
            KlineStalledAtFlinkRule(),
            ComponentDownRule(),
            FlinkBackpressureRule(),
            ConfigurationMismatchRule(),
        ),
    )
    gateway = ToolGateway(repository, tools)
    return LiveInspectionService(
        repository=repository,
        diagnosis=diagnosis,
        planner=ReadOnlyInspectionPlanner(),
        collector=InspectionCollector(gateway),
    )
