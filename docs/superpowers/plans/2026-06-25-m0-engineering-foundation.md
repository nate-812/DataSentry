# DataSentry M0 工程基础实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立可在干净环境运行的 Python 工程基础，使 CLI 能创建一次模拟巡检，并将 Inspection、Observation、Finding 及其 Evidence 写入 SQLite 后完整读回。

**Architecture:** 使用 Python 3.12、`src` 布局和 Pydantic v2 定义与基础设施解耦的领域模型；使用标准库 `sqlite3`、显式 Repository Protocol 和包内版本化 SQL 完成首版持久化；使用 Typer 提供数据库升级、模拟巡检和巡检读取命令。M0 只实现本地确定性流程，不接生产服务器、LLM、FastAPI、Web、Prometheus 或写操作执行器。

**Tech Stack:** Python 3.12、Pydantic 2、pydantic-settings、Typer、structlog、pytest、pytest-cov、Ruff、mypy、GitHub Actions、Gitleaks

---

## 1. 范围与完成定义

### 1.1 M0 必须交付

- 可安装的 `datasentry` Python 包和 `datasentry` CLI。
- 环境变量驱动的配置，前缀统一为 `DATASENTRY_`。
- JSON 结构化日志、敏感字段脱敏和统一异常基类。
- `Inspection`、`Observation`、`Evidence`、`Finding`、`Incident`、`Operation` 领域模型及受限枚举。
- SQLite 迁移执行器和首版数据库结构。
- Repository Protocol 与 SQLite 实现。
- CLI 命令：
  - `datasentry db upgrade`
  - `datasentry inspection simulate`
  - `datasentry inspection show INSPECTION_ID`
- 单元测试、SQLite 集成测试和 CLI 端到端测试。
- GitHub CI：格式检查、静态检查、类型检查、测试、覆盖率和秘密扫描。
- README 的本地开发与演示说明。

### 1.2 M0 明确不做

- 不接入 StreamLake 生产服务器、SSH、Flink、Kafka、Doris、Redis、MySQL 或日志。
- 不实现知识路由、血缘遍历和诊断规则；这些属于 M1。
- 不实现 FastAPI、后台 Worker、Web 页面、消息通知或 LLM；这些属于 M3/M4。
- 不实现审批、Runbook、自动重启、补数、配置修改、Savepoint 恢复或任意 Shell。
- 不引入 ORM、Alembic 或 PostgreSQL；Repository 边界允许后续替换存储实现。

### 1.3 验收场景

在全新虚拟环境执行：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
datasentry db upgrade --database-path /tmp/datasentry-m0.db
datasentry inspection simulate \
  --database-path /tmp/datasentry-m0.db \
  --question "M0 模拟巡检"
datasentry inspection show <simulate 输出的 inspection_id> \
  --database-path /tmp/datasentry-m0.db
```

预期：

- 数据库升级命令退出码为 `0`，输出当前 schema 版本 `1`。
- 模拟命令退出码为 `0`，输出合法 JSON。
- JSON 中包含一个 `completed` Inspection、一个 Observation，以及一个带 `confirmed` Evidence 的 `info` Finding。
- `show` 读回的数据与 `simulate` 保存的数据一致。
- 数据库中不存在凭据、Token、Cookie、私钥或真实生产连接信息。

## 2. 文件结构与职责

```text
data-sentry-agent/
├── .github/
│   └── workflows/
│       └── ci.yml
├── pyproject.toml
├── src/
│   └── datasentry/
│       ├── __init__.py                 # 包版本
│       ├── __main__.py                 # python -m datasentry
│       ├── config.py                   # DATASENTRY_ 环境配置
│       ├── errors.py                   # 稳定错误码和安全错误信息
│       ├── logging.py                  # structlog 配置与递归脱敏
│       ├── cli/
│       │   ├── __init__.py
│       │   └── app.py                  # Typer 根命令与子命令
│       ├── domain/
│       │   ├── __init__.py             # 领域类型公共导出
│       │   ├── common.py               # UTC、ID、基础模型
│       │   ├── enums.py                # 状态、严重级别和风险枚举
│       │   ├── inspection.py           # Inspection 与 Observation
│       │   ├── finding.py              # Evidence 与 Finding
│       │   ├── incident.py             # Incident
│       │   └── operation.py            # Operation
│       └── storage/
│           ├── __init__.py
│           ├── repository.py           # Repository Protocol
│           ├── sqlite.py               # sqlite3 实现和行映射
│           ├── migrations.py           # 迁移发现、校验和事务执行
│           └── sql/
│               ├── __init__.py
│               └── 0001_initial.sql
└── tests/
    ├── conftest.py                     # 固定 UTC 时间、模型工厂、临时 DB
    ├── unit/
    │   ├── test_config.py
    │   ├── test_errors.py
    │   ├── test_logging.py
    │   └── domain/
    │       ├── test_inspection.py
    │       ├── test_finding.py
    │       ├── test_incident.py
    │       └── test_operation.py
    ├── integration/
    │   └── storage/
    │       ├── test_migrations.py
    │       └── test_sqlite_repository.py
    └── scenarios/
        └── test_cli_simulated_inspection.py
```

说明：

- 不创建根目录 `migrations/`。SQL 放在 `datasentry.storage.sql` 包中，通过 `importlib.resources` 加载，确保 editable install、wheel 和 CI 中行为一致。
- SQLite 只出现在 `storage/sqlite.py` 和 `storage/migrations.py`；CLI 与后续诊断层只依赖 Repository Protocol。
- `Incident` 与 `Operation` 在 M0 只建立可验证的领域模型和存储往返能力，不实现生命周期服务、审批或执行。

## 3. 统一模型约定

### 3.1 ID 与时间

- 所有 ID 为应用层生成的 UUID4 字符串，不依赖 SQLite 自增主键。
- 所有时间必须带时区。
- 写入 SQLite 前统一转换为 UTC ISO-8601 字符串，例如 `2026-06-25T12:00:00+00:00`。
- 读取后恢复为带 UTC 时区的 `datetime`。

### 3.2 JSON

- `value`、证据列表、建议列表、参数和结果以 JSON TEXT 保存。
- 序列化固定使用 `sort_keys=True`、紧凑分隔符和 `ensure_ascii=False`，保证测试稳定。
- SQLite 连接启用 `PRAGMA foreign_keys = ON` 和 `PRAGMA busy_timeout = 5000`。

### 3.3 枚举

```python
class EvidenceStatus(StrEnum):
    CONFIRMED = "confirmed"
    INFERRED = "inferred"
    UNKNOWN = "unknown"
    HISTORICAL = "historical"


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class InspectionStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class IncidentStatus(StrEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    AWAITING_APPROVAL = "awaiting_approval"
    MITIGATING = "mitigating"
    VERIFYING = "verifying"
    RESOLVED = "resolved"
    BLOCKED = "blocked"
    ESCALATED = "escalated"


class OperationRisk(StrEnum):
    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    FORBIDDEN = "forbidden"


class OperationStatus(StrEnum):
    REQUESTED = "requested"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    RUNNING = "running"
    VERIFYING = "verifying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
```

## 4. 分任务实施步骤

### Task 1：建立 Python 包、开发工具和最小导入测试

**Files:**

- Create: `pyproject.toml`
- Create: `src/datasentry/__init__.py`
- Create: `tests/unit/test_package.py`
- Modify: `.gitignore`

- [ ] **Step 1：先写包导入失败测试**

```python
from datasentry import __version__


def test_package_exposes_version() -> None:
    assert __version__ == "0.1.0"
```

- [ ] **Step 2：验证测试在包未创建时失败**

Run:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install pytest
pytest tests/unit/test_package.py -q
```

Expected: FAIL，错误包含 `ModuleNotFoundError: No module named 'datasentry'`。

- [ ] **Step 3：创建项目元数据和包版本**

`pyproject.toml` 必须包含：

```toml
[build-system]
requires = ["hatchling>=1.27,<2"]
build-backend = "hatchling.build"

[project]
name = "datasentry-agent"
version = "0.1.0"
description = "Evidence-driven operations agent for StreamLake"
readme = "README.md"
requires-python = ">=3.12,<3.14"
dependencies = [
  "pydantic>=2.11,<3",
  "pydantic-settings>=2.9,<3",
  "structlog>=25.1,<26",
  "typer>=0.16,<1",
]

[project.optional-dependencies]
dev = [
  "mypy>=1.16,<2",
  "pytest>=8.4,<9",
  "pytest-cov>=6.2,<7",
  "ruff>=0.12,<1",
]

[project.scripts]
datasentry = "datasentry.cli.app:main"

[tool.hatch.build.targets.wheel]
packages = ["src/datasentry"]

[tool.hatch.build]
include = [
  "src/datasentry/**/*.py",
  "src/datasentry/storage/sql/*.sql",
]

[tool.pytest.ini_options]
addopts = "-ra --strict-config --strict-markers"
testpaths = ["tests"]

[tool.coverage.run]
branch = true
source = ["datasentry"]

[tool.coverage.report]
show_missing = true
skip_covered = true

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM", "RUF"]

[tool.mypy]
python_version = "3.12"
strict = true
packages = ["datasentry"]
```

`src/datasentry/__init__.py`：

```python
"""DataSentry agent package."""

__version__ = "0.1.0"
```

在 `.gitignore` 增加：

```gitignore
# Local runtime state
var/
```

- [ ] **Step 4：安装开发依赖并验证最小测试**

Run:

```bash
python -m pip install -e '.[dev]'
pytest tests/unit/test_package.py -q
```

Expected: `1 passed`。

- [ ] **Step 5：检查格式、静态规则和类型**

Run:

```bash
ruff format --check .
ruff check .
mypy src
```

Expected: 三条命令均退出码 `0`。

- [ ] **Step 6：提交工程骨架**

```bash
git add pyproject.toml .gitignore src/datasentry/__init__.py tests/unit/test_package.py
git diff --cached --check
git commit -m "chore: scaffold Python project"
```

### Task 2：实现配置、异常和结构化日志

**Files:**

- Create: `src/datasentry/config.py`
- Create: `src/datasentry/errors.py`
- Create: `src/datasentry/logging.py`
- Create: `tests/unit/test_config.py`
- Create: `tests/unit/test_errors.py`
- Create: `tests/unit/test_logging.py`

- [ ] **Step 1：写配置测试**

覆盖以下行为：

```python
def test_settings_use_safe_local_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.environment == "development"
    assert settings.database_path == Path("var/datasentry.db")
    assert settings.log_level == "INFO"
    assert settings.log_format == "json"


def test_settings_read_datasentry_prefixed_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATASENTRY_DATABASE_PATH", "/tmp/custom.db")
    monkeypatch.setenv("DATASENTRY_LOG_LEVEL", "DEBUG")
    settings = Settings(_env_file=None)
    assert settings.database_path == Path("/tmp/custom.db")
    assert settings.log_level == "DEBUG"
```

- [ ] **Step 2：写异常和日志脱敏测试**

```python
def test_datasentry_error_exposes_stable_safe_payload() -> None:
    error = DataSentryError(
        code="storage.unavailable",
        message="Database is unavailable",
        details={"database": "local"},
    )
    assert error.to_dict() == {
        "code": "storage.unavailable",
        "message": "Database is unavailable",
        "details": {"database": "local"},
    }


def test_redact_sensitive_values_recursively() -> None:
    event = {
        "token": "secret-token",
        "nested": {
            "authorization": "Bearer abc",
            "component": "flink",
        },
        "items": [{"password": "secret-password"}],
    }
    assert redact_sensitive_values(event) == {
        "token": "[REDACTED]",
        "nested": {
            "authorization": "[REDACTED]",
            "component": "flink",
        },
        "items": [{"password": "[REDACTED]"}],
    }
```

敏感键集合固定为：

```python
{
    "access_key",
    "api_key",
    "authorization",
    "cookie",
    "password",
    "private_key",
    "secret",
    "secret_key",
    "token",
}
```

- [ ] **Step 3：运行测试并确认失败**

Run:

```bash
pytest tests/unit/test_config.py tests/unit/test_errors.py tests/unit/test_logging.py -q
```

Expected: FAIL，原因是三个模块尚不存在。

- [ ] **Step 4：实现配置**

`Settings` 的公开契约：

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DATASENTRY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    database_path: Path = Path("var/datasentry.db")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "console"] = "json"
```

模块只负责解析配置，不在 import 时创建目录、打开数据库或修改全局日志。

- [ ] **Step 5：实现异常**

```python
class DataSentryError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


class ConfigurationError(DataSentryError):
    pass


class StorageError(DataSentryError):
    pass


class NotFoundError(DataSentryError):
    pass
```

- [ ] **Step 6：实现日志配置和递归脱敏**

核心实现：

```python
SENSITIVE_KEYS = frozenset(
    {
        "access_key",
        "api_key",
        "authorization",
        "cookie",
        "password",
        "private_key",
        "secret",
        "secret_key",
        "token",
    }
)


def redact_sensitive_values(
    value: object,
    *,
    parent_key: str | None = None,
) -> object:
    if parent_key is not None and parent_key.lower() in SENSITIVE_KEYS:
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {
            str(key): redact_sensitive_values(item, parent_key=str(key))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive_values(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive_values(item) for item in value)
    return value


def _redact_event(
    logger: object,
    method_name: str,
    event_dict: MutableMapping[str, object],
) -> MutableMapping[str, object]:
    redacted = redact_sensitive_values(event_dict)
    if not isinstance(redacted, MutableMapping):
        raise TypeError("structured log event must be a mutable mapping")
    return redacted


def configure_logging(*, level: str, log_format: Literal["json", "console"]) -> None:
    renderer: structlog.types.Processor
    if log_format == "json":
        renderer = structlog.processors.JSONRenderer(sort_keys=True)
    else:
        renderer = structlog.dev.ConsoleRenderer()

    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, level),
        stream=sys.stderr,
        force=True,
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _redact_event,
            renderer,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
```

实现要求：

- 字典键按小写匹配敏感键集合。
- 支持嵌套 `Mapping`、`list` 和 `tuple`。
- JSON 模式使用 `structlog.processors.JSONRenderer`。
- console 模式使用 `structlog.dev.ConsoleRenderer`。
- 每条日志包含 ISO-8601 UTC 时间、级别和事件名。
- 不自动记录 Settings 全量内容。

- [ ] **Step 7：运行单元测试和质量检查**

Run:

```bash
pytest tests/unit/test_config.py tests/unit/test_errors.py tests/unit/test_logging.py -q
ruff format --check .
ruff check .
mypy src
```

Expected: 全部通过。

- [ ] **Step 8：提交基础横切能力**

```bash
git add src/datasentry/config.py src/datasentry/errors.py src/datasentry/logging.py \
  tests/unit/test_config.py tests/unit/test_errors.py tests/unit/test_logging.py
git diff --cached --check
git commit -m "feat: add configuration and structured logging"
```

### Task 3：定义领域枚举与核心模型

**Files:**

- Create: `src/datasentry/domain/__init__.py`
- Create: `src/datasentry/domain/common.py`
- Create: `src/datasentry/domain/enums.py`
- Create: `src/datasentry/domain/inspection.py`
- Create: `src/datasentry/domain/finding.py`
- Create: `src/datasentry/domain/incident.py`
- Create: `src/datasentry/domain/operation.py`
- Create: `tests/conftest.py`
- Create: `tests/unit/domain/test_inspection.py`
- Create: `tests/unit/domain/test_finding.py`
- Create: `tests/unit/domain/test_incident.py`
- Create: `tests/unit/domain/test_operation.py`

- [ ] **Step 1：建立共享测试工厂**

`tests/conftest.py` 固定：

```python
@pytest.fixture
def observed_at() -> datetime:
    return datetime(2026, 6, 25, 12, 0, tzinfo=UTC)


@pytest.fixture
def inspection_id() -> str:
    return "11111111-1111-4111-8111-111111111111"
```

- [ ] **Step 2：写领域模型校验测试**

测试必须覆盖：

- naive `datetime` 被拒绝。
- 空 `question`、`claim`、`component`、`metric_or_fact` 被拒绝。
- `finished_at < started_at` 被拒绝。
- completed Inspection 必须有 `finished_at`。
- Evidence 状态只能来自 `EvidenceStatus`。
- Finding 至少包含一条 Evidence。
- resolved Incident 必须有 `resolved_at`。
- Operation 的 `FORBIDDEN` 风险不能进入 `APPROVED`、`RUNNING`、`VERIFYING` 或 `SUCCEEDED`。
- 模型 `model_dump(mode="json")` 输出可直接 JSON 序列化。

代表性测试：

```python
def test_completed_inspection_requires_finished_at(observed_at: datetime) -> None:
    with pytest.raises(ValidationError):
        Inspection(
            id="11111111-1111-4111-8111-111111111111",
            question="M0 inspection",
            scope=["simulation"],
            status=InspectionStatus.COMPLETED,
            started_at=observed_at,
        )


def test_finding_requires_evidence(observed_at: datetime) -> None:
    with pytest.raises(ValidationError):
        Finding(
            id="33333333-3333-4333-8333-333333333333",
            inspection_id="11111111-1111-4111-8111-111111111111",
            severity=Severity.INFO,
            status=EvidenceStatus.CONFIRMED,
            claim="Simulation completed",
            impact="No production impact",
            recommendation="Proceed to M1",
            unknowns=[],
            evidence=[],
            created_at=observed_at,
        )
```

- [ ] **Step 3：运行领域测试并确认失败**

Run:

```bash
pytest tests/unit/domain -q
```

Expected: FAIL，错误指向缺失的 `datasentry.domain` 模块。

- [ ] **Step 4：实现严格基础模型**

`common.py`：

```python
class DomainModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


def new_id() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(UTC)


def require_aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include timezone information")
    return value.astimezone(UTC)
```

- [ ] **Step 5：实现模型公开字段**

```python
class Inspection(DomainModel):
    id: str = Field(default_factory=new_id)
    question: str = Field(min_length=1)
    scope: list[str] = Field(default_factory=list)
    status: InspectionStatus = InspectionStatus.RUNNING
    summary: str | None = None
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None


class Observation(DomainModel):
    id: str = Field(default_factory=new_id)
    inspection_id: str
    component: str = Field(min_length=1)
    metric_or_fact: str = Field(min_length=1)
    value: JsonValue
    source: str = Field(min_length=1)
    target: str | None = None
    observed_at: datetime = Field(default_factory=utc_now)


class Evidence(DomainModel):
    claim: str = Field(min_length=1)
    status: EvidenceStatus
    source: str = Field(min_length=1)
    target: str | None = None
    observed_at: datetime
    summary: str = Field(min_length=1)


class Finding(DomainModel):
    id: str = Field(default_factory=new_id)
    inspection_id: str
    severity: Severity
    status: EvidenceStatus
    claim: str = Field(min_length=1)
    evidence: list[Evidence] = Field(min_length=1)
    impact: str = Field(min_length=1)
    recommendation: str = Field(min_length=1)
    unknowns: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class Incident(DomainModel):
    id: str = Field(default_factory=new_id)
    title: str = Field(min_length=1)
    symptom: str = Field(min_length=1)
    status: IncidentStatus = IncidentStatus.OPEN
    severity: Severity
    root_cause: str | None = None
    opened_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    resolved_at: datetime | None = None


class Operation(DomainModel):
    id: str = Field(default_factory=new_id)
    incident_id: str | None = None
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    risk: OperationRisk
    status: OperationStatus = OperationStatus.REQUESTED
    requester: str = Field(min_length=1)
    approver: str | None = None
    result: dict[str, JsonValue] | None = None
    requested_at: datetime = Field(default_factory=utc_now)
    approved_at: datetime | None = None
    executed_at: datetime | None = None
    verified_at: datetime | None = None
```

`JsonValue` 为递归类型别名：

```python
JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
```

- [ ] **Step 6：实现跨字段校验**

使用 Pydantic `model_validator(mode="after")`：

- Inspection 校验完成时间和状态。
- Incident 校验 `updated_at >= opened_at`，resolved 状态要求 `resolved_at`。
- Operation 校验 forbidden 状态限制；有 `approved_at` 必须有 approver；时间顺序必须为 requested ≤ approved ≤ executed ≤ verified。

- [ ] **Step 7：运行领域测试和类型检查**

Run:

```bash
pytest tests/unit/domain -q
ruff format --check .
ruff check .
mypy src
```

Expected: 全部通过。

- [ ] **Step 8：提交领域模型**

```bash
git add src/datasentry/domain tests/conftest.py tests/unit/domain
git diff --cached --check
git commit -m "feat: define core domain models"
```

### Task 4：实现 SQLite 迁移框架和首版 schema

**Files:**

- Create: `src/datasentry/storage/__init__.py`
- Create: `src/datasentry/storage/migrations.py`
- Create: `src/datasentry/storage/sql/__init__.py`
- Create: `src/datasentry/storage/sql/0001_initial.sql`
- Create: `tests/integration/storage/test_migrations.py`

- [ ] **Step 1：写迁移集成测试**

测试要求：

```python
def test_upgrade_creates_schema_and_records_version(tmp_path: Path) -> None:
    database_path = tmp_path / "datasentry.db"
    version = upgrade_database(database_path)
    assert version == 1

    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {
            "schema_migrations",
            "inspections",
            "observations",
            "findings",
            "incidents",
            "operations",
        } <= tables


def test_upgrade_is_idempotent(tmp_path: Path) -> None:
    database_path = tmp_path / "datasentry.db"
    assert upgrade_database(database_path) == 1
    assert upgrade_database(database_path) == 1


def test_foreign_keys_are_enforced(tmp_path: Path) -> None:
    database_path = tmp_path / "datasentry.db"
    upgrade_database(database_path)
    with connect(database_path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO observations (
                    id, inspection_id, component, metric_or_fact,
                    value_json, source, target, observed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "22222222-2222-4222-8222-222222222222",
                    "missing",
                    "simulation",
                    "status",
                    '"ok"',
                    "cli",
                    None,
                    "2026-06-25T12:00:00+00:00",
                ),
            )
```

- [ ] **Step 2：运行迁移测试并确认失败**

Run:

```bash
pytest tests/integration/storage/test_migrations.py -q
```

Expected: FAIL，原因是迁移模块不存在。

- [ ] **Step 3：编写首版 SQL**

`0001_initial.sql`：

```sql
CREATE TABLE inspections (
    id TEXT PRIMARY KEY,
    question TEXT NOT NULL CHECK (length(trim(question)) > 0),
    scope_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    summary TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE TABLE observations (
    id TEXT PRIMARY KEY,
    inspection_id TEXT NOT NULL,
    component TEXT NOT NULL CHECK (length(trim(component)) > 0),
    metric_or_fact TEXT NOT NULL CHECK (length(trim(metric_or_fact)) > 0),
    value_json TEXT NOT NULL,
    source TEXT NOT NULL CHECK (length(trim(source)) > 0),
    target TEXT,
    observed_at TEXT NOT NULL,
    FOREIGN KEY (inspection_id) REFERENCES inspections(id) ON DELETE CASCADE
);

CREATE TABLE findings (
    id TEXT PRIMARY KEY,
    inspection_id TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
    status TEXT NOT NULL CHECK (
        status IN ('confirmed', 'inferred', 'unknown', 'historical')
    ),
    claim TEXT NOT NULL CHECK (length(trim(claim)) > 0),
    evidence_json TEXT NOT NULL,
    impact TEXT NOT NULL CHECK (length(trim(impact)) > 0),
    recommendation TEXT NOT NULL CHECK (length(trim(recommendation)) > 0),
    unknowns_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (inspection_id) REFERENCES inspections(id) ON DELETE CASCADE
);

CREATE TABLE incidents (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL CHECK (length(trim(title)) > 0),
    symptom TEXT NOT NULL CHECK (length(trim(symptom)) > 0),
    status TEXT NOT NULL CHECK (
        status IN (
            'open',
            'investigating',
            'awaiting_approval',
            'mitigating',
            'verifying',
            'resolved',
            'blocked',
            'escalated'
        )
    ),
    severity TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
    root_cause TEXT,
    opened_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE operations (
    id TEXT PRIMARY KEY,
    incident_id TEXT,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    version TEXT NOT NULL CHECK (length(trim(version)) > 0),
    parameters_json TEXT NOT NULL,
    risk TEXT NOT NULL CHECK (risk IN ('L0', 'L1', 'L2', 'L3', 'forbidden')),
    status TEXT NOT NULL CHECK (
        status IN (
            'requested',
            'awaiting_approval',
            'approved',
            'running',
            'verifying',
            'succeeded',
            'failed',
            'rejected',
            'cancelled'
        )
    ),
    requester TEXT NOT NULL CHECK (length(trim(requester)) > 0),
    approver TEXT,
    result_json TEXT,
    requested_at TEXT NOT NULL,
    approved_at TEXT,
    executed_at TEXT,
    verified_at TEXT,
    FOREIGN KEY (incident_id) REFERENCES incidents(id) ON DELETE SET NULL
);

CREATE INDEX idx_inspections_started_at
    ON inspections(started_at);
CREATE INDEX idx_observations_inspection_id
    ON observations(inspection_id);
CREATE INDEX idx_findings_inspection_id
    ON findings(inspection_id);
CREATE INDEX idx_incidents_status_updated_at
    ON incidents(status, updated_at);
CREATE INDEX idx_operations_status_requested_at
    ON operations(status, requested_at);
```

- [ ] **Step 4：实现迁移执行器**

公开接口和执行逻辑：

```python
def connect(database_path: Path) -> sqlite3.Connection:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def current_schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations"
    ).fetchone()
    if row is None:
        return 0
    return int(row["version"])


def upgrade_database(database_path: Path) -> int:
    with connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        connection.commit()
        applied = current_schema_version(connection)
        migration_root = resources.files("datasentry.storage.sql")
        migrations = sorted(
            (
                resource
                for resource in migration_root.iterdir()
                if resource.name[:4].isdigit() and resource.name.endswith(".sql")
            ),
            key=lambda resource: resource.name,
        )
        for migration in migrations:
            version = int(migration.name[:4])
            if version <= applied:
                continue
            script = migration.read_text(encoding="utf-8")
            transactional_script = (
                "BEGIN IMMEDIATE;\n"
                f"{script}\n"
                "INSERT INTO schema_migrations(version, applied_at) "
                f"VALUES ({version}, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));\n"
                "COMMIT;"
            )
            try:
                connection.executescript(transactional_script)
            except sqlite3.Error as error:
                if connection.in_transaction:
                    connection.rollback()
                raise StorageError(
                    code="storage.migration_failed",
                    message="Database migration failed",
                    details={
                        "database_path": str(database_path),
                        "version": version,
                    },
                ) from error
            applied = version
        return applied
```

执行约束：

- 自动创建数据库父目录。
- 建立连接后设置 `row_factory = sqlite3.Row`、`foreign_keys = ON`、`busy_timeout = 5000`。
- 先创建 `schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)`。
- 按四位数字前缀排序迁移资源。
- 单个迁移脚本和版本记录在同一事务中提交。
- 迁移失败时回滚并抛出错误码 `storage.migration_failed`。
- 错误 details 只包含版本和数据库路径，不包含 SQL 全文。

- [ ] **Step 5：运行迁移测试**

Run:

```bash
pytest tests/integration/storage/test_migrations.py -q
```

Expected: 全部通过。

- [ ] **Step 6：验证 SQL 文件会进入 wheel**

Run:

```bash
python -m build
python -c "import zipfile; from pathlib import Path; wheel=next(Path('dist').glob('*.whl')); z=zipfile.ZipFile(wheel); assert any(name.endswith('storage/sql/0001_initial.sql') for name in z.namelist())"
```

在执行本步骤前，将 `build>=1.2,<2` 加入 `project.optional-dependencies.dev`。

Expected: 两条命令均退出码 `0`。

- [ ] **Step 7：提交迁移基础**

```bash
git add pyproject.toml src/datasentry/storage tests/integration/storage/test_migrations.py
git diff --cached --check
git commit -m "feat: add SQLite schema migrations"
```

### Task 5：实现 Repository Protocol 与 SQLite 往返

**Files:**

- Create: `src/datasentry/storage/repository.py`
- Create: `src/datasentry/storage/sqlite.py`
- Create: `tests/integration/storage/test_sqlite_repository.py`
- Modify: `src/datasentry/storage/__init__.py`

- [ ] **Step 1：写 Inspection 聚合往返测试**

```python
def test_save_and_get_inspection_aggregate(
    repository: SQLiteRepository,
    inspection: Inspection,
    observation: Observation,
    finding: Finding,
) -> None:
    repository.save_inspection(inspection)
    repository.add_observation(observation)
    repository.add_finding(finding)

    aggregate = repository.get_inspection(inspection.id)

    assert aggregate.inspection == inspection
    assert aggregate.observations == [observation]
    assert aggregate.findings == [finding]
```

同时覆盖：

- 不存在的 ID 抛 `NotFoundError(code="storage.inspection_not_found")`。
- 重复 ID 抛 `StorageError(code="storage.conflict")`。
- Observation/Finding 引用不存在 Inspection 时转换为稳定 `StorageError`，不把原始 SQL 暴露给调用方。
- Incident 保存、更新、读取往返。
- Operation 保存、更新、读取往返。
- Repository 关闭后再次调用抛 `StorageError(code="storage.closed")`。

- [ ] **Step 2：运行 Repository 测试并确认失败**

Run:

```bash
pytest tests/integration/storage/test_sqlite_repository.py -q
```

Expected: FAIL，原因是 Repository 尚未实现。

- [ ] **Step 3：定义 Repository Protocol 和聚合返回类型**

```python
@dataclass(frozen=True, slots=True)
class InspectionAggregate:
    inspection: Inspection
    observations: list[Observation]
    findings: list[Finding]


class Repository(Protocol):
    def save_inspection(self, inspection: Inspection) -> None:
        raise NotImplementedError

    def add_observation(self, observation: Observation) -> None:
        raise NotImplementedError

    def add_finding(self, finding: Finding) -> None:
        raise NotImplementedError

    def get_inspection(self, inspection_id: str) -> InspectionAggregate:
        raise NotImplementedError

    def save_incident(self, incident: Incident) -> None:
        raise NotImplementedError

    def update_incident(self, incident: Incident) -> None:
        raise NotImplementedError

    def get_incident(self, incident_id: str) -> Incident:
        raise NotImplementedError

    def save_operation(self, operation: Operation) -> None:
        raise NotImplementedError

    def update_operation(self, operation: Operation) -> None:
        raise NotImplementedError

    def get_operation(self, operation_id: str) -> Operation:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError
```

- [ ] **Step 4：实现 SQLiteRepository 生命周期**

```python
class SQLiteRepository:
    def __init__(self, database_path: Path) -> None:
        upgrade_database(database_path)
        self._connection = connect(database_path)
        self._closed = False

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
```

实现要求：

- 每个公开写方法使用显式事务。
- 捕获 `sqlite3.IntegrityError` 并映射到稳定错误码。
- 所有查询使用参数绑定。
- JSON 编解码集中到私有函数，不散落在各方法。
- 行到模型的映射集中为 `_row_to_inspection`、`_row_to_observation`、`_row_to_finding`、`_row_to_incident`、`_row_to_operation`。
- Finding 的 `evidence_json` 使用 `list[Evidence]` 验证后构造。

- [ ] **Step 5：运行 Repository 测试**

Run:

```bash
pytest tests/integration/storage/test_sqlite_repository.py -q
```

Expected: 全部通过。

- [ ] **Step 6：运行完整存储测试和类型检查**

Run:

```bash
pytest tests/integration/storage -q
ruff format --check .
ruff check .
mypy src
```

Expected: 全部通过。

- [ ] **Step 7：提交 Repository**

```bash
git add src/datasentry/storage tests/integration/storage/test_sqlite_repository.py
git diff --cached --check
git commit -m "feat: persist inspections and operations"
```

### Task 6：实现 CLI 数据库升级与模拟巡检闭环

**Files:**

- Create: `src/datasentry/cli/__init__.py`
- Create: `src/datasentry/cli/app.py`
- Create: `src/datasentry/__main__.py`
- Create: `tests/scenarios/test_cli_simulated_inspection.py`

- [ ] **Step 1：写 CLI 场景测试**

使用 `typer.testing.CliRunner`，覆盖：

```python
def test_simulate_then_show_round_trip(tmp_path: Path) -> None:
    database_path = tmp_path / "datasentry.db"

    simulate = runner.invoke(
        app,
        [
            "inspection",
            "simulate",
            "--database-path",
            str(database_path),
            "--question",
            "M0 simulated inspection",
        ],
    )
    assert simulate.exit_code == 0
    created = json.loads(simulate.stdout)
    assert created["inspection"]["status"] == "completed"
    assert created["observations"][0]["component"] == "datasentry"
    assert created["findings"][0]["status"] == "confirmed"

    show = runner.invoke(
        app,
        [
            "inspection",
            "show",
            created["inspection"]["id"],
            "--database-path",
            str(database_path),
        ],
    )
    assert show.exit_code == 0
    assert json.loads(show.stdout) == created
```

还要覆盖：

- `db upgrade` 返回包含实际数据库路径和 `"schema_version": 1` 的 JSON。
- `inspection show missing-id` 退出码为 `2`，stderr 是安全 JSON 错误，不含 traceback 和 SQL。
- `python -m datasentry --help` 与 console script 使用同一 app。

- [ ] **Step 2：运行场景测试并确认失败**

Run:

```bash
pytest tests/scenarios/test_cli_simulated_inspection.py -q
```

Expected: FAIL，原因是 CLI 模块不存在。

- [ ] **Step 3：实现命令树**

公开结构：

```text
datasentry
├── db
│   └── upgrade
└── inspection
    ├── simulate
    └── show
```

入口：

```python
app = typer.Typer(no_args_is_help=True)
db_app = typer.Typer(no_args_is_help=True)
inspection_app = typer.Typer(no_args_is_help=True)
app.add_typer(db_app, name="db")
app.add_typer(inspection_app, name="inspection")


def main() -> None:
    app()
```

- [ ] **Step 4：实现模拟数据**

`inspection simulate` 必须使用同一个 `observed_at = utc_now()` 创建：

```python
inspection = Inspection(
    question=question,
    scope=["simulation"],
    status=InspectionStatus.COMPLETED,
    summary="M0 local persistence simulation completed",
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
    claim="M0 local simulation completed",
    status=EvidenceStatus.CONFIRMED,
    source="datasentry_cli",
    target="local",
    observed_at=observed_at,
    summary="The CLI created and read back a local SQLite inspection",
)

finding = Finding(
    inspection_id=inspection.id,
    severity=Severity.INFO,
    status=EvidenceStatus.CONFIRMED,
    claim="DataSentry M0 persistence path is operational",
    evidence=[evidence],
    impact="Local engineering foundation only; no production system was queried",
    recommendation="Proceed with M1 after M0 review",
    unknowns=["Production connectivity is outside M0 scope"],
    created_at=observed_at,
)
```

保存顺序固定为 Inspection → Observation → Finding，再通过 `get_inspection` 读回并输出，不直接输出内存中的原对象。

- [ ] **Step 5：统一 CLI JSON 和错误行为**

- stdout 只输出结果 JSON。
- 日志输出到 stderr。
- JSON 使用 UTF-8、缩进 2 空格和排序键。
- 捕获 `DataSentryError`，stderr 输出 `error.to_dict()`，退出码 `2`。
- 未知异常记录脱敏后的结构化错误，用户侧只返回：

```json
{
  "code": "internal.error",
  "details": {},
  "message": "An unexpected error occurred"
}
```

- [ ] **Step 6：运行 CLI 场景测试**

Run:

```bash
pytest tests/scenarios/test_cli_simulated_inspection.py -q
datasentry --help
python -m datasentry --help
```

Expected: 测试通过；两个帮助命令均显示 `db` 和 `inspection`。

- [ ] **Step 7：手工运行 M0 验收场景**

Run:

```bash
rm -f /tmp/datasentry-m0.db
datasentry db upgrade --database-path /tmp/datasentry-m0.db
datasentry inspection simulate \
  --database-path /tmp/datasentry-m0.db \
  --question "M0 acceptance inspection"
```

Expected: 两条命令退出码 `0`；模拟输出明确包含 `"production_access": false`。

- [ ] **Step 8：提交 CLI 闭环**

```bash
git add src/datasentry/cli src/datasentry/__main__.py tests/scenarios
git diff --cached --check
git commit -m "feat: add simulated inspection CLI"
```

### Task 7：增加 CI、覆盖率门槛和秘密扫描

**Files:**

- Create: `.github/workflows/ci.yml`
- Modify: `pyproject.toml`

- [ ] **Step 1：先在本地执行拟定 CI 命令**

Run:

```bash
ruff format --check .
ruff check .
mypy src
pytest tests -q --cov=datasentry --cov-report=term-missing --cov-fail-under=90
```

Expected: 全部通过，覆盖率不低于 `90%`。

- [ ] **Step 2：补足缺失测试而不降低门槛**

若覆盖率不足，只补充以下允许范围内的测试：

- 配置环境变量覆盖。
- 日志 console/json renderer 选择。
- 模型跨字段校验失败分支。
- Migration rollback 和重复执行。
- Repository not-found、closed、constraint 映射。
- CLI 安全错误输出。

不得使用 `# pragma: no cover` 隐藏正常业务分支；只允许排除 `if TYPE_CHECKING` 和 `if __name__ == "__main__"`。

- [ ] **Step 3：编写 GitHub Actions 工作流**

工作流要求：

```yaml
name: CI

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  quality:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - run: python -m pip install --upgrade pip
      - run: python -m pip install -e '.[dev]'
      - run: ruff format --check .
      - run: ruff check .
      - run: mypy src
      - run: pytest tests -q --cov=datasentry --cov-report=term-missing --cov-fail-under=90

  secrets:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

- [ ] **Step 4：验证工作流语法和本地门槛**

Run:

```bash
python -c "import pathlib, yaml; yaml.safe_load(pathlib.Path('.github/workflows/ci.yml').read_text())"
ruff format --check .
ruff check .
mypy src
pytest tests -q --cov=datasentry --cov-report=term-missing --cov-fail-under=90
```

为 YAML 验证将 `PyYAML>=6.0,<7` 加入 dev dependencies。

Expected: 全部通过。

- [ ] **Step 5：提交 CI**

```bash
git add .github/workflows/ci.yml pyproject.toml tests
git diff --cached --check
git commit -m "ci: add quality and secret checks"
```

### Task 8：更新使用文档和项目状态

**Files:**

- Modify: `README.md`
- Modify: `docs/PROJECT_STATUS.md`

- [ ] **Step 1：更新 README**

README 增加：

- M0 能力与明确边界。
- Python 3.12 环境创建和 editable install。
- 三个 CLI 命令示例。
- `DATASENTRY_DATABASE_PATH`、`DATASENTRY_LOG_LEVEL`、`DATASENTRY_LOG_FORMAT` 配置表。
- 本地验证命令。
- “模拟巡检不访问生产环境”的醒目标注。

- [ ] **Step 2：更新 PROJECT_STATUS 当前快照**

仅在全部 M0 验证通过后更新：

- 总体状态：M0 已完成，等待评审或进入 M1。
- 当前阶段：M0 完成。
- 当前工作：M0 验收与评审。
- 下一里程碑：M1 知识驱动诊断。
- M0 阶段状态改为已完成。
- 变更日志记录工程骨架、领域模型、SQLite、CLI 和 CI 完成。
- 保留“尚未接入生产服务器”的事实。

- [ ] **Step 3：运行文档与全量验证**

Run:

```bash
git diff --check
ruff format --check .
ruff check .
mypy src
pytest tests -q --cov=datasentry --cov-report=term-missing --cov-fail-under=90
rm -f /tmp/datasentry-m0-final.db
datasentry db upgrade --database-path /tmp/datasentry-m0-final.db
datasentry inspection simulate \
  --database-path /tmp/datasentry-m0-final.db \
  --question "M0 final verification"
```

Expected:

- 所有静态检查和测试通过。
- 覆盖率不低于 `90%`。
- CLI 验收输出合法 JSON，且明确未访问生产环境。

- [ ] **Step 4：检查秘密和提交内容**

Run:

```bash
git status --short
git diff
git grep -nEi '(password|token|secret|api[_-]?key|private[_-]?key)' -- \
  ':!docs/**' ':!knowledge/**' ':!tests/**'
```

Expected:

- 只包含 M0 计划内文件。
- 搜索命中仅为脱敏键名、占位配置或 Gitleaks 工作流变量，不含真实秘密。

- [ ] **Step 5：提交文档与状态**

```bash
git add README.md docs/PROJECT_STATUS.md
git diff --cached --check
git commit -m "docs: document M0 engineering foundation"
```

## 5. 提交顺序

实现时严格按以下顺序形成可恢复检查点：

1. `chore: scaffold Python project`
2. `feat: add configuration and structured logging`
3. `feat: define core domain models`
4. `feat: add SQLite schema migrations`
5. `feat: persist inspections and operations`
6. `feat: add simulated inspection CLI`
7. `ci: add quality and secret checks`
8. `docs: document M0 engineering foundation`

每个提交前必须执行该任务列出的最小测试；第 8 个提交前执行全量验证。不要把失败或覆盖率未达标的提交推送为稳定检查点。

## 6. 分支、推送与 GitHub 顺序

M0 属于包含工程骨架、数据模型和 CI 的较大功能，执行阶段使用独立分支：

```bash
git fetch origin
git status --short --branch
git switch -c feat/m0-engineering-foundation
```

如果执行时使用 Worktree，先调用 `superpowers:using-git-worktrees`，并在隔离目录创建同名分支。

稳定推送点：

1. 完成 Task 1～3 且单元测试、ruff、mypy 通过后第一次推送。
2. 完成 Task 4～6 且 SQLite 与 CLI 场景测试通过后第二次推送。
3. 完成 Task 7～8 且全量验证通过后最终推送并创建 Pull Request。

每次推送前：

```bash
git fetch origin
git log --oneline --decorate --graph --max-count=12 --all
git status --short --branch
```

若远端同名分支出现非本地提交或与 `main` 分叉，停止并报告，不强推、不重写远端历史。最终合并 Pull Request 需要用户明确批准。

## 7. 最终验证矩阵

| 需求 | 自动验证 | 人工验证 |
|---|---|---|
| 包可安装 | editable install、wheel build | `datasentry --help` |
| 配置安全默认值 | `test_config.py` | 检查无真实 `.env` |
| 结构化日志与脱敏 | `test_logging.py` | stderr 日志抽查 |
| 领域模型约束 | `tests/unit/domain/` | 与总体设计字段对照 |
| SQLite 迁移 | `test_migrations.py` | 查看 schema version |
| Repository 往返 | `test_sqlite_repository.py` | 无 SQLite 细节泄漏到 CLI |
| CLI 模拟巡检 | `test_cli_simulated_inspection.py` | 执行 M0 验收命令 |
| 代码质量 | Ruff、mypy | `git diff --check` |
| 覆盖率 | pytest-cov ≥ 90% | 检查未滥用排除 |
| 秘密扫描 | Gitleaks job | 提交前关键词扫描 |
| 生产边界 | 场景数据断言 `production_access=false` | 确认无网络/SSH/生产配置 |

## 8. 计划自审

### 8.1 总体设计覆盖

- Python 工程、依赖管理、配置：Task 1～2。
- 结构化日志、异常体系、测试框架：Task 1～2。
- Observation、Evidence、Finding、Incident、Operation：Task 3。
- SQLite Repository 和迁移：Task 4～5。
- CLI：Task 6。
- GitHub CI、格式、静态检查、单元测试、秘密扫描：Task 7。
- README、状态同步和完整验收：Task 8。
- CLI 创建模拟巡检并写入读回：Task 6 场景测试和最终验收矩阵。
- 不接生产、LLM、Web：范围排除和场景断言均已明确。

### 8.2 类型与命名一致性

- `Evidence.status`、`Finding.status` 均使用 `EvidenceStatus`。
- `InspectionAggregate` 统一包含 `inspection`、`observations`、`findings`。
- CLI、Repository 和测试统一使用 `database_path`。
- SQL JSON 字段与模型映射固定为 `value_json`、`scope_json`、`evidence_json`、`unknowns_json`、`parameters_json`、`result_json`。
- 所有时间均使用带时区 `datetime`，数据库中统一保存 UTC ISO-8601。

### 8.3 风险控制

- 不读取工作区外秘密，不创建真实 `.env`。
- 不执行网络、SSH、数据库远程连接或生产探测。
- 不允许 CLI 接受任意 SQL 或 Shell。
- 不在日志、异常或数据库中保存真实凭据。
- 不在 M0 提前实现 Incident 自动流转或 Operation 执行。
