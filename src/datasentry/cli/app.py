"""用于本地开发和应急巡检的 Typer 命令树。"""

import json
from collections.abc import Callable
from enum import StrEnum
from json import JSONDecodeError
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import TypeAdapter, ValidationError
from typer import rich_utils
from typer._click.core import Context
from typer._click.formatting import HelpFormatter
from typer.core import TyperCommand, TyperGroup, TyperOption

from datasentry.config import Settings
from datasentry.diagnosis import (
    ComponentDownRule,
    ConfigurationMismatchRule,
    DiagnosisResult,
    DiagnosisService,
    FlinkBackpressureRule,
    KlineStalledAtFlinkRule,
)
from datasentry.domain import (
    Evidence,
    EvidenceStatus,
    Finding,
    Inspection,
    InspectionStatus,
    Observation,
    Severity,
)
from datasentry.domain.common import utc_now
from datasentry.errors import DataSentryError, DiagnosisError
from datasentry.knowledge import (
    KnowledgeIndex,
    KnowledgeRouter,
    build_streamlake_lineage,
)
from datasentry.logging import configure_logging, get_logger
from datasentry.notifications import (
    AlertmanagerPayload,
    NotificationService,
    parse_alertmanager_payload,
)
from datasentry.storage import InspectionAggregate, SQLiteRepository, upgrade_database
from datasentry.tools import (
    LiveInspectionResult,
    TargetCatalog,
    build_live_inspection_service,
)


def _show_help(ctx: Context, parameter: object, value: bool) -> None:
    """输出帮助页面并退出。"""
    del parameter
    if value and not ctx.resilient_parsing:
        typer.echo(ctx.get_help(), color=ctx.color)
        ctx.exit()


def _get_chinese_help_option(
    command: TyperCommand | TyperGroup,
    ctx: Context,
) -> TyperOption | None:
    """创建中文说明的帮助选项。"""
    help_option_names = command.get_help_option_names(ctx)
    if not help_option_names or not command.add_help_option:
        return None
    if command._help_option is None:
        command._help_option = TyperOption(
            param_decls=help_option_names,
            is_flag=True,
            expose_value=False,
            is_eager=True,
            help="显示帮助信息并退出。",
            callback=_show_help,
            required=False,
        )
    return command._help_option


class ChineseTyperCommand(TyperCommand):
    """使用中文帮助文案的 Typer Command。"""

    def get_help_option(self, ctx: Context) -> TyperOption | None:
        """返回中文帮助选项。"""
        return _get_chinese_help_option(self, ctx)

    def format_usage(self, ctx: Context, formatter: HelpFormatter) -> None:
        """输出中文用法标题。"""
        pieces = self.collect_usage_pieces(ctx)
        formatter.write_usage(ctx.command_path, " ".join(pieces), prefix="用法: ")


class ChineseTyperGroup(TyperGroup):
    """使用中文帮助文案的 Typer Group。"""

    def get_help_option(self, ctx: Context) -> TyperOption | None:
        """返回中文帮助选项。"""
        return _get_chinese_help_option(self, ctx)

    def format_usage(self, ctx: Context, formatter: HelpFormatter) -> None:
        """输出中文用法标题。"""
        pieces = self.collect_usage_pieces(ctx)
        formatter.write_usage(ctx.command_path, " ".join(pieces), prefix="用法: ")


def _configure_chinese_help_text() -> None:
    """配置 Typer Rich 帮助页面中的中文固定文案。"""
    translations: dict[str, Any] = {
        "ARGUMENTS_PANEL_TITLE": "参数",
        "OPTIONS_PANEL_TITLE": "选项",
        "COMMANDS_PANEL_TITLE": "命令",
        "ERRORS_PANEL_TITLE": "错误",
        "ABORTED_TEXT": "已中止。",
        "REQUIRED_LONG_STRING": "[必填]",
        "DEFAULT_STRING": "[默认值：{}]",
        "ENVVAR_STRING": "[环境变量：{}]",
        "RICH_HELP": "可运行 [blue]'{command_path} {help_option}'[/] 查看帮助。",
    }
    for name, value in translations.items():
        setattr(rich_utils, name, value)


_configure_chinese_help_text()

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    cls=ChineseTyperGroup,
)
db_app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    cls=ChineseTyperGroup,
)
inspection_app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    cls=ChineseTyperGroup,
)
notification_app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    cls=ChineseTyperGroup,
)
app.add_typer(db_app, name="db")
app.add_typer(inspection_app, name="inspection")
app.add_typer(notification_app, name="notification")


class NotificationOutputFormat(StrEnum):
    """通知模拟命令支持的输出格式。"""

    WECOM = "wecom"
    GENERIC = "generic"

DatabasePathOption = Annotated[
    Path | None,
    typer.Option(
        "--database-path",
        help="SQLite 数据库路径，默认使用 DATASENTRY_DATABASE_PATH。",
    ),
]
ObservationsFileOption = Annotated[
    Path,
    typer.Option(
        "--observations-file",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="本地模拟 Observation JSON 文件。",
    ),
]
KnowledgeRootOption = Annotated[
    Path,
    typer.Option(
        "--knowledge-root",
        file_okay=False,
        dir_okay=True,
        readable=True,
        help="知识库根目录，目录内必须包含 INDEX.md。",
    ),
]
TargetsFileOption = Annotated[
    Path | None,
    typer.Option(
        "--targets-file",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="目标配置 TOML，默认使用 DATASENTRY_TARGETS_FILE。",
    ),
]
PayloadFileOption = Annotated[
    Path,
    typer.Option(
        "--payload-file",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Alertmanager Webhook JSON 载荷文件。",
    ),
]

OBSERVATION_LIST_ADAPTER = TypeAdapter(list[Observation])


def _database_path(value: Path | None) -> Path:
    if value is not None:
        return value
    return Settings().database_path


def _write_json(value: object, *, error: bool = False) -> None:
    typer.echo(
        json.dumps(
            value,
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
        ),
        err=error,
    )


def _aggregate_payload(aggregate: InspectionAggregate) -> dict[str, object]:
    return {
        "inspection": aggregate.inspection.model_dump(mode="json"),
        "observations": [
            observation.model_dump(mode="json") for observation in aggregate.observations
        ],
        "findings": [finding.model_dump(mode="json") for finding in aggregate.findings],
    }


def _diagnosis_payload(result: DiagnosisResult) -> dict[str, object]:
    return {
        "route": result.route.model_dump(mode="json"),
        "knowledge": [item.model_dump(mode="json") for item in result.knowledge],
        "lineage_checkpoints": [
            item.model_dump(mode="json") for item in result.lineage_checkpoints
        ],
        "aggregate": _aggregate_payload(result.aggregate),
    }


def _live_inspection_payload(result: LiveInspectionResult) -> dict[str, object]:
    payload = _diagnosis_payload(result.diagnosis)
    payload["tool_invocations"] = [item.model_dump(mode="json") for item in result.tool_invocations]
    return payload


def _load_observations(path: Path) -> list[Observation]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return OBSERVATION_LIST_ADAPTER.validate_python(value)
    except (OSError, JSONDecodeError, ValidationError) as error:
        raise DiagnosisError(
            code="diagnosis.invalid_observations",
            message="模拟 Observation 文件无效",
        ) from error


def _load_alertmanager_payload(path: Path) -> AlertmanagerPayload:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, JSONDecodeError) as error:
        raise DataSentryError(
            code="notification.invalid_payload",
            message="Alertmanager Webhook 载荷无效",
        ) from error
    return parse_alertmanager_payload(value)


def _build_notification_service(
    *,
    repository: SQLiteRepository,
    targets_file: Path | None,
    knowledge_root: Path,
) -> NotificationService:
    targets_path = targets_file if targets_file is not None else Settings().targets_file
    targets = TargetCatalog.load(targets_path)
    runner = build_live_inspection_service(
        repository=repository,
        targets=targets,
        knowledge_root=knowledge_root,
    )
    return NotificationService(diagnosis_runner=runner)


def _run_json(action: Callable[[], object]) -> None:
    try:
        _write_json(action())
    except DataSentryError as error:
        _write_json(error.to_dict(), error=True)
        raise typer.Exit(code=2) from error
    except Exception as error:
        get_logger(__name__).error(
            "cli.unexpected_error",
            error_type=type(error).__name__,
        )
        _write_json(
            {
                "code": "internal.error",
                "details": {},
                "message": "发生未预期的内部错误",
            },
            error=True,
        )
        raise typer.Exit(code=1) from error


@db_app.command("upgrade", cls=ChineseTyperCommand)
def db_upgrade(database_path: DatabasePathOption = None) -> None:
    """执行尚未应用的 SQLite 迁移。"""
    path = _database_path(database_path)
    _run_json(
        lambda: {
            "database_path": str(path),
            "schema_version": upgrade_database(path),
        }
    )


@inspection_app.command("simulate", cls=ChineseTyperCommand)
def inspection_simulate(
    question: Annotated[
        str,
        typer.Option("--question", help="记录到模拟巡检中的问题。"),
    ],
    database_path: DatabasePathOption = None,
) -> None:
    """创建模拟巡检，将其持久化后从本地 SQLite 读回。"""
    path = _database_path(database_path)

    def simulate() -> dict[str, object]:
        observed_at = utc_now()
        inspection = Inspection(
            question=question,
            scope=["simulation"],
            status=InspectionStatus.COMPLETED,
            summary="M0 本地持久化模拟巡检已完成",
            started_at=observed_at,
            finished_at=observed_at,
        )
        observation = Observation(
            inspection_id=inspection.id,
            component="datasentry",
            metric_or_fact="m0_simulation_status",
            value={"status": "ok", "production_access": False},
            source="datasentry_cli",
            target="local",
            observed_at=observed_at,
        )
        evidence = Evidence(
            claim="M0 本地模拟巡检已完成",
            status=EvidenceStatus.CONFIRMED,
            source="datasentry_cli",
            target="local",
            observed_at=observed_at,
            summary="CLI 已创建本地 SQLite 巡检记录，并从数据库中成功读回",
        )
        finding = Finding(
            inspection_id=inspection.id,
            severity=Severity.INFO,
            status=EvidenceStatus.CONFIRMED,
            claim="DataSentry M0 持久化链路运行正常",
            evidence=[evidence],
            impact="仅验证本地工程基础，未查询生产系统",
            recommendation="M0 评审通过后进入 M1",
            unknowns=["生产连接能力不在 M0 范围内"],
            created_at=observed_at,
        )
        with SQLiteRepository(path) as repository:
            running = inspection.model_copy(
                update={
                    "status": InspectionStatus.RUNNING,
                    "summary": None,
                    "finished_at": None,
                }
            )
            repository.start_inspection(running)
            aggregate = repository.complete_inspection(
                inspection,
                [observation],
                [finding],
            )
            return _aggregate_payload(aggregate)

    _run_json(simulate)


@inspection_app.command("show", cls=ChineseTyperCommand)
def inspection_show(
    inspection_id: Annotated[str, typer.Argument(help="巡检记录 ID。")],
    database_path: DatabasePathOption = None,
) -> None:
    """读取已持久化的巡检聚合记录。"""
    path = _database_path(database_path)

    def show() -> dict[str, object]:
        with SQLiteRepository(path) as repository:
            return _aggregate_payload(repository.get_inspection(inspection_id))

    _run_json(show)


@inspection_app.command("diagnose", cls=ChineseTyperCommand)
def inspection_diagnose(
    question: Annotated[
        str,
        typer.Option("--question", help="需要执行知识驱动诊断的问题。"),
    ],
    observations_file: ObservationsFileOption,
    knowledge_root: KnowledgeRootOption,
    database_path: DatabasePathOption = None,
) -> None:
    """使用本地模拟 Observation 执行 M1 知识驱动诊断。"""
    path = _database_path(database_path)

    def diagnose() -> dict[str, object]:
        knowledge_index = KnowledgeIndex.load(knowledge_root)
        observations = _load_observations(observations_file)
        with SQLiteRepository(path) as repository:
            service = DiagnosisService(
                repository=repository,
                knowledge_index=knowledge_index,
                router=KnowledgeRouter(knowledge_index),
                lineage_graph=build_streamlake_lineage(),
                rules=(
                    KlineStalledAtFlinkRule(),
                    ComponentDownRule(),
                    FlinkBackpressureRule(),
                    ConfigurationMismatchRule(),
                ),
            )
            result = service.diagnose(question, observations)
            return _diagnosis_payload(result)

    _run_json(diagnose)


@inspection_app.command("run", cls=ChineseTyperCommand)
def inspection_run(
    question: Annotated[
        str,
        typer.Option("--question", help="需要执行真实只读巡检的问题。"),
    ],
    targets_file: TargetsFileOption = None,
    knowledge_root: KnowledgeRootOption = Path("knowledge"),
    database_path: DatabasePathOption = None,
) -> None:
    """执行真实只读巡检，不执行任何生产写操作。"""
    settings = Settings()
    path = _database_path(database_path)
    targets_path = targets_file or settings.targets_file

    def run() -> dict[str, object]:
        targets = TargetCatalog.load(targets_path)
        with SQLiteRepository(path) as repository:
            service = build_live_inspection_service(
                repository=repository,
                targets=targets,
                knowledge_root=knowledge_root,
            )
            return _live_inspection_payload(service.run(question))

    _run_json(run)


@notification_app.command("simulate", cls=ChineseTyperCommand)
def notification_simulate(
    payload_file: PayloadFileOption,
    output_format: Annotated[
        NotificationOutputFormat,
        typer.Option(
            "--format",
            help="输出格式：wecom 为企业微信 Markdown，generic 为通用 Webhook JSON。",
        ),
    ] = NotificationOutputFormat.WECOM,
    targets_file: TargetsFileOption = None,
    knowledge_root: KnowledgeRootOption = Path("knowledge"),
    database_path: DatabasePathOption = None,
) -> None:
    """使用 Alertmanager 本地载荷模拟告警诊断通知。"""
    path = _database_path(database_path)

    def simulate() -> dict[str, object]:
        payload = _load_alertmanager_payload(payload_file)
        with SQLiteRepository(path) as repository:
            service = _build_notification_service(
                repository=repository,
                targets_file=targets_file,
                knowledge_root=knowledge_root,
            )
            result = service.build(payload)
        if output_format is NotificationOutputFormat.WECOM:
            return result.wecom_markdown
        return result.generic_webhook

    _run_json(simulate)


def main() -> None:
    """配置进程日志并运行 CLI。"""
    settings = Settings()
    configure_logging(level=settings.log_level, log_format=settings.log_format)
    app()
