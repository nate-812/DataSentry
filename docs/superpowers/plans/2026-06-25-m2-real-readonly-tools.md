# DataSentry M2 真实只读工具实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不开放任意 Shell、任意 SQL 或任何生产写操作的前提下，为 DataSentry 接入 Flink、Spring API、AI Engine、三台主机、Kafka、Doris、Redis、MySQL 和有限日志的真实只读查询，并将结果转换为 M1 已定义的标准 Observation，完成一次可审计、可持久化、局部失败可降级的端到端真实巡检。

**Architecture:** 保留 M1 的 `DiagnosisService(list[Observation])` 规则边界，在其前方新增同步白名单工具网关、固定目标目录、受控传输层和确定性巡检采集器。HTTP、SSH、MySQL 协议和 Redis 的实现差异全部封装在适配器内部；网关统一完成参数校验、超时、有限重试、输出限制、脱敏、审计和失败归一化。真实巡检先创建 `running` Inspection，工具调用逐条审计，最后以单个 SQLite 事务完成 Observation、Finding 和 Inspection 状态更新；单个工具失败只增加明确未知项，不阻断其他工具和规则。

**Tech Stack:** Python 3.12、Pydantic 2、Typer、httpx、Paramiko、PyMySQL、redis-py、标准库 `tomllib`、SQLite Repository、pytest、Ruff、mypy

---

## 1. 范围与完成定义

### 1.1 M2 必须交付

- 新增固定白名单工具：
  - `get_flink_jobs`
  - `get_flink_job`
  - `get_flink_checkpoints`
  - `get_flink_backpressure`
  - `get_api_health`
  - `get_host_status`
  - `get_service_status`
  - `get_kafka_topics`
  - `get_kafka_topic`
  - `get_kafka_group`
  - `get_doris_table_freshness`
  - `get_redis_key_sample`
  - `get_mysql_table_sample`
  - `get_recent_logs`
- 所有工具参数由 Pydantic 封闭模型校验；主机、组件、Job、Topic、Group、表、Redis Key Pattern、API 服务和日志源只能来自代码目录或目标配置中的允许值。
- 生产目标使用本地 TOML 配置，仓库只提交占位示例；密码和私钥内容只从环境变量或本地文件注入。
- SSH 严格校验 host key，只执行代码中固定命令模板，不接受用户或模型提供的命令文本。
- Doris/MySQL 只执行代码中固定 `SELECT`、`SHOW`、`DESCRIBE` 查询，不接受 SQL 字符串。
- Redis 只允许 `INFO`、`DBSIZE`、小批量 `SCAN`、`TYPE`、`TTL` 和按类型读取的有限样本；禁止 `KEYS`。
- 日志只允许配置中登记的组件日志源，最多最近 200 行或最近 30 分钟；输出超过字节上限时拒绝该工具结果并记录稳定超限错误。
- HTTP、SSH、数据库和 Redis 均设置连接超时与读取超时；只对可判定为瞬时的只读传输错误重试一次。
- 工具输出在写日志、SQLite、CLI JSON 或进入诊断规则前统一脱敏。
- 新增工具调用审计模型与 SQLite 表，记录脱敏参数、状态、耗时、Observation 数量和稳定错误码，不记录原始秘密或完整底层异常。
- 修复当前 Inspection 聚合多次写入缺少事务的问题：
  - 先保存 `running` Inspection。
  - 完成时在一个事务中更新 Inspection 并插入全部 Observation、Finding。
  - 失败时将 Inspection 标记为 `failed`，保留已完成的工具审计。
- 新增真实巡检 CLI：

```text
datasentry inspection run \
  --question "为什么K线不更新" \
  --targets-file config/targets.toml \
  --knowledge-root knowledge \
  --database-path /var/lib/datasentry/datasentry.db
```

- `inspection run` 返回路由、知识、血缘、工具审计摘要、Observation、Finding 和未知项。
- 使用脱敏契约 fixture 和模拟传输完成自动测试；生产现场验收作为人工步骤执行，不在 CI 中连接生产。

### 1.2 M2 明确不做

- 不执行 `start`、`stop`、`restart`、`flink run`、`cancel`、`savepoint`、补数、配置修改、数据删除或任何写操作。
- 不调用 `/root/bin/*.sh` 的写操作；脚本源码审计仍留到 M6。
- 不提供自由文本 Shell、自由 SQL、自由 URL、自由日志路径或自由 Redis Pattern。
- 不读取 Shell History、SSH 私钥内容、`.env` 内容、云 Metadata、完整进程环境变量或系统钥匙串。
- 不部署 Prometheus、Grafana、Alertmanager、Loki 或 Alloy；这些属于 M3。
- 不引入 FastAPI、异步 Worker、LLM、Web、Incident 自动聚合或通知。
- 不把 Kafka Consumer Group 不可见解释为正常；工具只报告事实和稳定未知项。
- 不把 Milvus 未运行判定为故障；AI Engine 健康工具必须允许明确的降级状态。
- 不在仓库中提交真实 IP 以外的新敏感拓扑、用户名、密码、Token、私钥、连接串或生产日志。

### 1.3 M2 首个端到端验收场景

执行 Kline 数据新鲜度巡检时，采集器至少调用：

1. `get_host_status(data1)`。
2. `get_service_status(data1, collector)`。
3. `get_flink_jobs()`。
4. `get_flink_job(kline)`。
5. `get_flink_checkpoints(kline)`。
6. `get_flink_backpressure(kline)`。
7. `get_kafka_topic(binance.trade.raw)`。
8. `get_doris_table_freshness(kline_1min)`。
9. `get_api_health(spring_api)`。

预期：

- 每个成功工具产生带 `source`、`target` 和 UTC `observed_at` 的 Observation。
- Kafka、Flink、Doris 输出兼容 M1 已有事实名：
  - `topic_advancing`
  - `kline_job_state`
  - `checkpoint_consecutive_failures`
  - `backpressure_level`
  - `kline_freshness_seconds`
- 任一非关键工具失败时，其他工具继续执行，最终 Finding 的 `unknowns` 包含工具名、目标和稳定错误码。
- 所有工具调用都能从 SQLite 读回审计摘要。
- CLI 输出和数据库中不出现配置 fixture 中植入的密码、Token、AK/SK、私钥片段或 URL 用户信息。

## 2. 方案对比与设计决策

### 2.1 方案对比

| 方案 | 优点 | 风险 | 结论 |
|---|---|---|---|
| 在 `DiagnosisService` 中直接连接各组件 | 文件少、短期接线快 | 规则层与网络、凭据、重试和脱敏耦合，难以测试和审计 | 不采用 |
| 提供通用 SSH/SQL/HTTP 工具 | 适配范围广 | 实质上开放任意命令、任意查询和任意 URL，违反第一版安全边界 | 禁止 |
| 白名单网关 + 固定高层工具 + 受控传输 | 参数和权限边界清楚，可独立契约测试，能保持 M1 Observation 接口 | 初期文件和适配器数量较多 | 采用 |

### 2.2 保持同步执行和低并发

M2 继续使用同步 CLI 与同步 Repository。一次巡检按固定顺序执行，避免在尚未引入 Worker、连接池和并发写控制前扩大复杂度，也避免同时对生产组件形成突发查询。每个工具自身有严格超时，后续 M4 引入异步任务时再在工具网关外增加并发调度。

### 2.3 目标配置与秘密分离

仓库中的 `config/targets.example.toml` 只保存非秘密目标、端口、允许的组件和“秘密所在环境变量名”。真实 `config/targets.toml` 被 `.gitignore` 忽略。配置加载器解析 TOML 后，再从进程环境读取密码；SSH 私钥只传路径给 Paramiko，DataSentry 不读取并持久化其内容。

### 2.4 高层工具而不是通用客户端

上层调用 `get_doris_table_freshness(table="kline_1min")`，不能调用 `execute_sql(sql=...)`；调用 `get_recent_logs(component="spring_api")`，不能调用 `ssh(command=...)`。适配器内部可以复用 HTTP、SSH、PyMySQL 和 Redis 传输，但这些传输类不从 CLI 或模型接收自由文本命令。

### 2.5 工具失败是数据，不是全局异常

参数无效、配置缺失和安全策略拒绝属于调用前错误，返回 CLI 稳定错误并且不访问目标。连接超时、认证失败、上游 5xx、解析失败和输出超限属于单工具失败，转换为 `ToolOutcome(status="failed")` 和巡检未知项；采集器继续执行剩余工具。

### 2.6 审计数据先脱敏再持久化

`ToolInvocation.parameters`、`error_message` 和日志摘要只保存脱敏结果。原始响应只在适配器局部变量中存在，解析、裁剪和脱敏后才创建 Observation。结构化日志只记录工具名、目标别名、稳定错误码、耗时和数量，不记录连接串或底层异常字符串。

### 2.7 先修复 Inspection 生命周期

真实工具会让巡检持续时间和失败面显著增加。M2 在接入生产适配器前先增加 `start_inspection`、`complete_inspection` 和 `fail_inspection`，保证最终聚合原子写入，并让中途失败留下可解释的 `failed` Inspection 和工具审计，而不是看似完成但缺少部分子记录的聚合。

### 2.8 契约 fixture 与生产现场分离

Flink REST、Spring API、AI Engine、Kafka CLI、Doris、MySQL、Redis 和日志输出都保存脱敏 fixture。CI 只运行解析器、模拟传输和场景测试。生产验收必须由用户提供只读凭据和本地目标配置，在明确的只读影子窗口手工执行。

## 3. 文件结构与职责

```text
config/
└── targets.example.toml            # 无秘密的目标配置示例
src/datasentry/
├── config.py                       # 增加 targets_file 和工具默认限制
├── domain/
│   └── tool.py                     # ToolName、ToolStatus、ToolInvocation
├── storage/
│   ├── repository.py               # Inspection 生命周期和工具审计接口
│   ├── sqlite.py                   # 原子完成巡检与工具审计实现
│   └── sql/
│       └── 0002_tool_invocations.sql
└── tools/
    ├── __init__.py                 # 公共导出
    ├── models.py                   # ToolCall、ToolOutcome、ToolFailure、限制
    ├── errors.py                   # ToolError 和稳定分类
    ├── redaction.py                # 深度脱敏和文本脱敏
    ├── targets.py                  # TOML 目标目录与秘密引用加载
    ├── gateway.py                  # 参数校验、执行、审计、失败隔离
    ├── planner.py                  # 问题类型/血缘到固定工具调用
    ├── collector.py                # 顺序执行计划并汇总 Observation/未知项
    ├── service.py                  # 真实采集与 DiagnosisService 编排
    ├── transports/
    │   ├── http.py                 # 受限 HTTP GET
    │   ├── ssh.py                  # 严格 host key、固定命令执行与输出上限
    │   ├── mysql.py                # 只读 MySQL 协议连接
    │   └── redis.py                # 受限 Redis 命令
    └── adapters/
        ├── flink.py                # Flink REST 解析与 Observation
        ├── api.py                  # Spring API/AI Engine 健康检查
        ├── host.py                 # 主机和服务状态固定命令
        ├── kafka.py                # Kafka list/describe/offset 固定命令
        ├── doris.py                # 固定数据新鲜度查询
        ├── redis.py                # INFO/DBSIZE/SCAN/TTL 样本
        ├── mysql.py                # 固定规则表样本和元数据
        └── logs.py                 # journal/file 最近日志
tests/
├── fixtures/contracts/
│   ├── flink/
│   ├── api/
│   ├── host/
│   ├── kafka/
│   ├── doris/
│   ├── redis/
│   ├── mysql/
│   └── logs/
├── unit/tools/
├── integration/tools/
├── integration/storage/
└── scenarios/
    └── test_cli_real_readonly_inspection.py
```

## 4. 核心契约

### 4.1 工具调用与结果

```python
from datetime import datetime
from enum import StrEnum

from pydantic import Field, JsonValue

from datasentry.domain.common import DomainModel, new_id, utc_now


class ToolName(StrEnum):
    GET_FLINK_JOBS = "get_flink_jobs"
    GET_FLINK_JOB = "get_flink_job"
    GET_FLINK_CHECKPOINTS = "get_flink_checkpoints"
    GET_FLINK_BACKPRESSURE = "get_flink_backpressure"
    GET_API_HEALTH = "get_api_health"
    GET_HOST_STATUS = "get_host_status"
    GET_SERVICE_STATUS = "get_service_status"
    GET_KAFKA_TOPICS = "get_kafka_topics"
    GET_KAFKA_TOPIC = "get_kafka_topic"
    GET_KAFKA_GROUP = "get_kafka_group"
    GET_DORIS_TABLE_FRESHNESS = "get_doris_table_freshness"
    GET_REDIS_KEY_SAMPLE = "get_redis_key_sample"
    GET_MYSQL_TABLE_SAMPLE = "get_mysql_table_sample"
    GET_RECENT_LOGS = "get_recent_logs"


class ToolStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ToolCall(DomainModel):
    id: str = Field(default_factory=new_id)
    name: ToolName
    target: str = Field(min_length=1)
    arguments: dict[str, JsonValue] = Field(default_factory=dict)


class ToolFailure(DomainModel):
    code: str = Field(pattern=r"^tool\.[a-z0-9_.]+$")
    message: str = Field(min_length=1)
    retryable: bool = False


class ToolOutcome(DomainModel):
    call: ToolCall
    status: ToolStatus
    observations: list[Observation] = Field(default_factory=list)
    failure: ToolFailure | None = None
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime = Field(default_factory=utc_now)
```

### 4.2 工具适配器和网关

```python
from collections.abc import Mapping
from typing import Protocol

from pydantic import JsonValue


class ReadOnlyTool(Protocol):
    name: ToolName

    def execute(
        self,
        *,
        inspection_id: str,
        target: str,
        arguments: Mapping[str, JsonValue],
    ) -> list[Observation]:
        """校验参数并执行一个固定只读工具。"""
        raise NotImplementedError


class ToolGateway:
    def __init__(
        self,
        repository: Repository,
        tools: tuple[ReadOnlyTool, ...],
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        """拒绝重复工具名并建立固定注册表。"""
        raise NotImplementedError

    def execute(self, inspection_id: str, call: ToolCall) -> ToolOutcome:
        """执行工具，审计成功或失败，并屏蔽预期工具异常。"""
        raise NotImplementedError
```

### 4.3 Inspection 生命周期

```python
class Repository(Protocol):
    def start_inspection(self, inspection: Inspection) -> None:
        """插入 running Inspection。"""
        raise NotImplementedError

    def complete_inspection(
        self,
        inspection: Inspection,
        observations: list[Observation],
        findings: list[Finding],
    ) -> InspectionAggregate:
        """在单个事务中更新完成状态并插入全部子记录。"""
        raise NotImplementedError

    def fail_inspection(self, inspection: Inspection) -> None:
        """将已存在的 running Inspection 更新为 failed。"""
        raise NotImplementedError

    def save_tool_invocation(self, invocation: ToolInvocation) -> None:
        """保存已脱敏的工具调用审计。"""
        raise NotImplementedError

    def list_tool_invocations(self, inspection_id: str) -> list[ToolInvocation]:
        """按开始时间和 ID 返回工具调用审计。"""
        raise NotImplementedError
```

### 4.4 真实巡检编排

```python
class CollectionResult(DomainModel):
    outcomes: list[ToolOutcome]
    observations: list[Observation]
    unknowns: list[str]


class LiveInspectionResult(DomainModel):
    diagnosis: DiagnosisResult
    tool_invocations: list[ToolInvocation]


class LiveInspectionService:
    def run(self, question: str) -> LiveInspectionResult:
        """准备诊断、保存 running 状态、采集真实 Observation 并完成诊断。"""
        raise NotImplementedError
```

## 5. 分任务实施步骤

### Task 1：建立 M2 分支并固化当前基线

**Files:**

- Modify: `docs/PROJECT_STATUS.md`

- [ ] **Step 1：确认工作区和远端基线**

Run:

```bash
git status --short --branch
git fetch origin
git log -5 --oneline --decorate
```

Expected:

- 工作区无未提交改动，或只有本计划与状态文档改动。
- `main` 与 `origin/main` 不存在未解释分叉。

- [ ] **Step 2：创建隔离功能分支**

Run:

```bash
git switch -c feat/m2-real-readonly-tools
```

Expected: 当前分支为 `feat/m2-real-readonly-tools`。

- [ ] **Step 3：运行完整基线验证**

Run:

```bash
.venv/bin/ruff format --check .
.venv/bin/ruff check .
.venv/bin/mypy src
.venv/bin/pytest tests -q -W error::ResourceWarning \
  --cov=datasentry \
  --cov-report=term-missing \
  --cov-fail-under=90
```

Expected: 全部退出码为 `0`；当前基线为 75 个测试通过、覆盖率不低于 90%。

- [ ] **Step 4：更新状态文档为 M2 实施中**

将当前阶段更新为 `M2：真实只读工具`，当前工作写明“实现工具安全基础和 Inspection 原子生命周期”，保留“尚未接入生产凭据”的事实。

- [ ] **Step 5：提交实施起点**

```bash
git add docs/PROJECT_STATUS.md
git diff --cached --check
git commit -m "docs: 启动 M2 真实只读工具实施"
```

### Task 2：实现原子 Inspection 生命周期和工具审计存储

**Files:**

- Create: `src/datasentry/domain/tool.py`
- Create: `src/datasentry/storage/sql/0002_tool_invocations.sql`
- Modify: `src/datasentry/domain/__init__.py`
- Modify: `src/datasentry/storage/repository.py`
- Modify: `src/datasentry/storage/sqlite.py`
- Modify: `src/datasentry/diagnosis/service.py`
- Modify: `src/datasentry/cli/app.py`
- Create: `tests/unit/domain/test_tool.py`
- Modify: `tests/integration/storage/test_migrations.py`
- Modify: `tests/integration/storage/test_sqlite_repository.py`
- Modify: `tests/unit/diagnosis/test_service.py`

- [ ] **Step 1：写 ToolInvocation 模型测试**

```python
def test_tool_invocation_requires_finished_time_not_before_started() -> None:
    with pytest.raises(ValidationError):
        ToolInvocation(
            inspection_id="inspection-1",
            tool_name=ToolName.GET_FLINK_JOBS,
            target="flink",
            parameters={},
            status=ToolStatus.SUCCEEDED,
            observation_count=1,
            started_at=NOW,
            finished_at=NOW - timedelta(seconds=1),
        )
```

模型字段固定为：

```python
class ToolInvocation(DomainModel):
    id: str = Field(default_factory=new_id)
    inspection_id: str = Field(min_length=1)
    tool_name: ToolName
    target: str = Field(min_length=1)
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    status: ToolStatus
    observation_count: int = Field(ge=0)
    error_code: str | None = None
    error_message: str | None = None
    started_at: datetime
    finished_at: datetime
    duration_ms: int = Field(ge=0)
```

- [ ] **Step 2：写迁移和审计读回测试**

```python
def test_upgrade_adds_tool_invocations_table(tmp_path: Path) -> None:
    database_path = tmp_path / "datasentry.db"

    assert upgrade_database(database_path) == 2

    with connect(database_path) as connection:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(tool_invocations)")
        }
    assert {"inspection_id", "tool_name", "parameters_json", "duration_ms"} <= columns
```

`0002_tool_invocations.sql` 使用外键关联 `inspections(id)`，并建立：

```sql
CREATE INDEX idx_tool_invocations_inspection_started
    ON tool_invocations(inspection_id, started_at);
```

- [ ] **Step 3：写原子完成回滚测试**

使用两个相同 Observation ID 调用 `complete_inspection`，断言抛出 `StorageError` 后：

```python
aggregate = repository.get_inspection(inspection.id)
assert aggregate.inspection.status is InspectionStatus.RUNNING
assert aggregate.observations == []
assert aggregate.findings == []
```

- [ ] **Step 4：运行测试确认失败**

Run:

```bash
.venv/bin/pytest \
  tests/unit/domain/test_tool.py \
  tests/integration/storage/test_migrations.py \
  tests/integration/storage/test_sqlite_repository.py \
  tests/unit/diagnosis/test_service.py -q
```

Expected: FAIL，错误包含缺少 `ToolInvocation` 或 Repository 新方法。

- [ ] **Step 5：实现 Inspection 生命周期**

`start_inspection` 只接受 `RUNNING`；`complete_inspection` 只接受 `COMPLETED` 且数据库现状为 `RUNNING`；`fail_inspection` 只接受 `FAILED`。状态不合法时抛出：

```text
storage.invalid_inspection_transition
```

`complete_inspection` 使用一个 `with connection:` 事务完成状态更新和全部子记录插入，内部复用私有 `_insert_observation`、`_insert_finding`，不再逐条提交。

- [ ] **Step 6：重构 DiagnosisService 保持旧接口兼容**

保留：

```python
def diagnose(
    self,
    question: str,
    observations: list[Observation],
    collection_unknowns: tuple[str, ...] = (),
) -> DiagnosisResult:
```

内部顺序改为：

1. 创建 `RUNNING` Inspection。
2. `repository.start_inspection()`。
3. 执行规则。
4. 将 `collection_unknowns` 去重追加到每个 Finding。
5. `repository.complete_inspection()`。
6. 任一规则或存储异常发生时，尽力 `fail_inspection()`，再抛原异常。

- [ ] **Step 7：迁移 M0 simulate 到原子接口**

`inspection simulate` 使用 `start_inspection` + `complete_inspection`，不得继续逐条调用旧的 `save_inspection/add_observation/add_finding`。

- [ ] **Step 8：验证兼容性**

Run:

```bash
.venv/bin/pytest tests/unit/diagnosis tests/integration/storage tests/scenarios -q
.venv/bin/ruff check src tests
.venv/bin/mypy src
```

Expected: 全部退出码为 `0`，M0/M1 CLI JSON 契约不变。

- [ ] **Step 9：提交存储检查点**

```bash
git add src/datasentry/domain src/datasentry/storage src/datasentry/diagnosis \
  src/datasentry/cli tests
git diff --cached --check
git commit -m "feat: 增加巡检原子生命周期与工具审计"
```

### Task 3：增加目标目录、秘密引用和安全默认限制

**Files:**

- Create: `config/targets.example.toml`
- Create: `src/datasentry/tools/__init__.py`
- Create: `src/datasentry/tools/targets.py`
- Modify: `src/datasentry/config.py`
- Modify: `.gitignore`
- Modify: `pyproject.toml`
- Create: `tests/unit/tools/test_targets.py`
- Modify: `tests/unit/test_config.py`

- [ ] **Step 1：写安全目标配置测试**

```python
def test_target_catalog_loads_aliases_without_resolving_secrets(
    tmp_path: Path,
) -> None:
    path = write_targets_file(tmp_path)

    catalog = TargetCatalog.load(path)

    assert catalog.host("data1").address == "192.0.2.10"
    assert catalog.ssh("data1").password_env == "TEST_SSH_PASSWORD"
    assert "secret-value" not in catalog.model_dump_json()
```

另测：

- 重复 alias。
- 未知 host 引用。
- 非正整数端口。
- HTTP URL 含用户名或密码。
- SSH 配置关闭 host key 校验。
- 日志路径不在允许根目录。
- `password_env` 名称不满足 `^[A-Z][A-Z0-9_]+$`。

- [ ] **Step 2：写秘密解析失败测试**

```python
def test_secret_resolver_reports_missing_environment_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TEST_DORIS_PASSWORD", raising=False)

    with pytest.raises(ConfigurationError) as raised:
        EnvironmentSecretResolver().require("TEST_DORIS_PASSWORD")

    assert raised.value.code == "configuration.secret_missing"
    assert "TEST_DORIS_PASSWORD" in raised.value.details.values()
```

错误中只允许出现环境变量名，不允许出现其他环境变量值。

- [ ] **Step 3：运行测试确认失败**

Run:

```bash
.venv/bin/pytest tests/unit/tools/test_targets.py tests/unit/test_config.py -q
```

Expected: FAIL，缺少 `TargetCatalog`。

- [ ] **Step 4：增加运行依赖**

在 `pyproject.toml` 运行依赖中增加：

```toml
"httpx>=0.28,<1",
"paramiko>=3.5,<5",
"PyMySQL>=1.1,<2",
"redis>=5,<7",
```

不增加 YAML 依赖；目标文件使用 Python 3.12 标准库 `tomllib`。

- [ ] **Step 5：实现配置模型**

至少定义：

```python
class ToolLimits(DomainModel):
    connect_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    read_timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    max_output_bytes: int = Field(default=65_536, ge=1_024, le=1_048_576)
    max_log_lines: int = Field(default=200, ge=1, le=200)
    max_log_minutes: int = Field(default=30, ge=1, le=30)
    retry_attempts: int = Field(default=1, ge=0, le=1)
```

目标类型包括 `HostTarget`、`HttpTarget`、`SshTarget`、`MySqlTarget`、`RedisTarget` 和 `LogSource`。真实秘密不作为模型字段。

- [ ] **Step 6：提交无秘密示例**

`config/targets.example.toml` 使用文档保留地址 `192.0.2.0/24` 或占位域名，密码只写：

```toml
password_env = "DATASENTRY_DORIS_PASSWORD"
```

`.gitignore` 增加：

```gitignore
config/targets.toml
config/targets.*.toml
!config/targets.example.toml
```

- [ ] **Step 7：验证配置与秘密扫描**

Run:

```bash
.venv/bin/pytest tests/unit/tools/test_targets.py tests/unit/test_config.py -q
.venv/bin/ruff check src/datasentry/tools tests/unit/tools
.venv/bin/mypy src
git diff --check
```

Expected: 全部退出码为 `0`。

- [ ] **Step 8：提交目标配置检查点**

```bash
git add .gitignore pyproject.toml config/targets.example.toml \
  src/datasentry/config.py src/datasentry/tools tests/unit/tools tests/unit/test_config.py
git diff --cached --check
git commit -m "feat: 增加只读目标目录与秘密引用"
```

### Task 4：实现脱敏、错误分类和白名单工具网关

**Files:**

- Create: `src/datasentry/tools/models.py`
- Create: `src/datasentry/tools/errors.py`
- Create: `src/datasentry/tools/redaction.py`
- Create: `src/datasentry/tools/gateway.py`
- Create: `tests/unit/tools/test_redaction.py`
- Create: `tests/unit/tools/test_gateway.py`

- [ ] **Step 1：写深度脱敏测试**

```python
def test_redact_value_masks_nested_secret_keys_and_url_credentials() -> None:
    value = {
        "password": "p@ss",
        "nested": {"access_key": "AK123", "safe": "ok"},
        "url": "http://user:token@example.test/path",
    }

    redacted = redact_value(value)

    assert redacted == {
        "password": "[REDACTED]",
        "nested": {"access_key": "[REDACTED]", "safe": "ok"},
        "url": "http://[REDACTED]@example.test/path",
    }
```

文本脱敏至少覆盖大小写不敏感的：

```text
password, passwd, secret, token, access_key, secret_key, ak, sk, authorization, cookie
```

并遮蔽 URL 用户信息、Bearer Token、常见 AK/SK 赋值和 PEM 私钥区块。

- [ ] **Step 2：写网关成功审计测试**

```python
def test_gateway_persists_redacted_success_audit(
    repository: Repository,
) -> None:
    tool = StubTool(
        name=ToolName.GET_API_HEALTH,
        observations=[observation()],
    )
    gateway = ToolGateway(repository, (tool,), clock=clock)

    outcome = gateway.execute(
        "inspection-1",
        ToolCall(
            name=ToolName.GET_API_HEALTH,
            target="spring_api",
            arguments={"token": "do-not-store", "service": "spring_api"},
        ),
    )

    assert outcome.status is ToolStatus.SUCCEEDED
    invocation = repository.list_tool_invocations("inspection-1")[0]
    assert invocation.parameters["token"] == "[REDACTED]"
    assert invocation.observation_count == 1
```

- [ ] **Step 3：写失败隔离和未知工具测试**

```python
def test_gateway_converts_tool_error_to_failed_outcome() -> None:
    tool = FailingTool(
        ToolError(
            code="tool.timeout",
            message="目标读取超时",
            retryable=True,
        )
    )

    outcome = gateway_for(tool).execute("inspection-1", call_for(tool.name))

    assert outcome.status is ToolStatus.FAILED
    assert outcome.failure is not None
    assert outcome.failure.code == "tool.timeout"
    assert outcome.observations == []
```

未注册工具返回 `tool.not_registered`，不得尝试动态导入或执行。

- [ ] **Step 4：运行测试确认失败**

Run:

```bash
.venv/bin/pytest \
  tests/unit/tools/test_redaction.py \
  tests/unit/tools/test_gateway.py -q
```

Expected: FAIL，缺少网关与脱敏模块。

- [ ] **Step 5：实现稳定错误分类**

`ToolError` 只允许以下公共类别：

```text
tool.configuration
tool.invalid_arguments
tool.policy_denied
tool.connection_failed
tool.authentication_failed
tool.timeout
tool.upstream_error
tool.parse_failed
tool.output_limit_exceeded
tool.not_registered
tool.internal_error
```

适配器可以增加更具体的后缀，但 CLI message 必须是中文安全摘要。

- [ ] **Step 6：实现 ToolGateway**

网关必须：

1. 构造时拒绝重复 `ToolName`。
2. 记录开始时间。
3. 调用固定适配器。
4. 校验每条 Observation 的 `inspection_id` 等于当前巡检。
5. 对 Observation 再执行结构化脱敏。
6. 捕获 `ToolError` 并生成失败 outcome。
7. 捕获未知异常，日志只记录异常类型，返回 `tool.internal_error`。
8. 无论成功失败都保存一条 `ToolInvocation`。

- [ ] **Step 7：验证安全基础**

Run:

```bash
.venv/bin/pytest tests/unit/tools -q
.venv/bin/ruff format --check src tests
.venv/bin/ruff check src tests
.venv/bin/mypy src
```

Expected: 全部退出码为 `0`。

- [ ] **Step 8：提交网关检查点**

```bash
git add src/datasentry/tools tests/unit/tools
git diff --cached --check
git commit -m "feat: 增加白名单工具网关与统一脱敏"
```

### Task 5：实现受限 HTTP 传输和 Flink REST 工具

**Files:**

- Create: `src/datasentry/tools/transports/__init__.py`
- Create: `src/datasentry/tools/transports/http.py`
- Create: `src/datasentry/tools/adapters/__init__.py`
- Create: `src/datasentry/tools/adapters/flink.py`
- Create: `tests/fixtures/contracts/flink/jobs_overview.json`
- Create: `tests/fixtures/contracts/flink/job_details.json`
- Create: `tests/fixtures/contracts/flink/checkpoints.json`
- Create: `tests/fixtures/contracts/flink/backpressure.json`
- Create: `tests/unit/tools/test_http_transport.py`
- Create: `tests/unit/tools/adapters/test_flink.py`

- [ ] **Step 1：写 HTTP 策略测试**

验证：

- 只允许 `GET`。
- URL 必须由已配置 base URL 和代码内固定 path 拼接。
- 禁止重定向到不同 host。
- 响应体超过 `max_output_bytes` 抛 `tool.output_limit_exceeded`。
- 连接/读取超时映射为 `tool.timeout`。
- 429、502、503、504 可重试一次；其他 4xx 不重试。

- [ ] **Step 2：写 Flink 契约解析测试**

```python
def test_get_flink_jobs_maps_kline_state_to_m1_fact(
    flink_tool: FlinkJobsTool,
) -> None:
    observations = flink_tool.execute(
        inspection_id="inspection-1",
        target="flink",
        arguments={},
    )

    kline = next(item for item in observations if item.metric_or_fact == "kline_job_state")
    assert kline.component == "flink"
    assert kline.value == {
        "job_id": "kline-job-id",
        "job_name": "streamlake-kline-aggregation",
        "state": "RUNNING",
    }
    assert kline.source == "flink_rest"
```

Checkpoint fixture 解析出：

```text
checkpoint_latest_completed_at
checkpoint_latest_duration_ms
checkpoint_latest_size_bytes
checkpoint_consecutive_failures
```

反压 fixture 解析出：

```text
backpressure_level
backpressure_vertices
```

输出只保留最多 20 个 Vertex 摘要。

- [ ] **Step 3：运行测试确认失败**

Run:

```bash
.venv/bin/pytest \
  tests/unit/tools/test_http_transport.py \
  tests/unit/tools/adapters/test_flink.py -q
```

Expected: FAIL，缺少 HTTP 与 Flink 实现。

- [ ] **Step 4：实现固定 Flink 端点**

只允许：

```text
/overview
/jobs/overview
/jobs/{job_id}
/jobs/{job_id}/checkpoints
/jobs/{job_id}/vertices/{vertex_id}/backpressure
```

Job 参数使用封闭枚举 `kline`、`whale`、`risk`，先通过 `/jobs/overview` 按稳定 Job 名解析 `job_id`。找不到 Job 时仍返回 `{"state": "MISSING"}` Observation，不作为工具失败。

- [ ] **Step 5：验证 Flink 工具**

Run:

```bash
.venv/bin/pytest tests/unit/tools/adapters/test_flink.py -q
.venv/bin/ruff check src/datasentry/tools tests/unit/tools
.venv/bin/mypy src
```

Expected: 全部退出码为 `0`。

- [ ] **Step 6：提交 Flink 检查点**

```bash
git add src/datasentry/tools tests/fixtures/contracts/flink tests/unit/tools
git diff --cached --check
git commit -m "feat: 接入 Flink REST 只读工具"
```

### Task 6：实现 Spring API 与 AI Engine 健康工具

**Files:**

- Create: `src/datasentry/tools/adapters/api.py`
- Create: `tests/fixtures/contracts/api/spring_health.json`
- Create: `tests/fixtures/contracts/api/spring_kline_latest.json`
- Create: `tests/fixtures/contracts/api/ai_health_degraded.json`
- Create: `tests/unit/tools/adapters/test_api.py`

- [ ] **Step 1：写健康与真实查询区分测试**

```python
def test_spring_health_requires_health_and_read_probe() -> None:
    observations = spring_tool.execute(
        inspection_id="inspection-1",
        target="spring_api",
        arguments={"service": "spring_api"},
    )

    assert fact(observations, "service_state").value == {"state": "RUNNING"}
    assert fact(observations, "api_read_probe").value["status"] == "ok"
```

如果健康接口成功但 Kline 只读探针失败，`service_state` 不能掩盖 `api_read_probe` 失败；适配器返回两条 Observation。

- [ ] **Step 2：写 AI 降级测试**

Milvus 不可用但 AI Engine 健康响应明确 `degraded` 时：

```python
assert fact(observations, "service_state").value == {
    "state": "RUNNING",
    "mode": "degraded",
}
assert fact(observations, "optional_dependency_state").value == {
    "dependency": "milvus",
    "state": "UNAVAILABLE_ALLOWED",
}
```

- [ ] **Step 3：实现固定 endpoint 目录**

endpoint 路径来自代码目录，不来自 CLI。若真实服务路径与 fixture 不同，只修改目标配置中的已批准 path 字段或代码目录并补契约测试，不允许用户提供完整 URL。

- [ ] **Step 4：验证并提交**

Run:

```bash
.venv/bin/pytest tests/unit/tools/adapters/test_api.py -q
.venv/bin/ruff check src tests
.venv/bin/mypy src
git add src/datasentry/tools/adapters/api.py tests/fixtures/contracts/api \
  tests/unit/tools/adapters/test_api.py
git diff --cached --check
git commit -m "feat: 接入业务 API 健康只读工具"
```

### Task 7：实现严格 SSH 传输、主机状态和服务状态工具

**Files:**

- Create: `src/datasentry/tools/transports/ssh.py`
- Create: `src/datasentry/tools/adapters/host.py`
- Create: `tests/fixtures/contracts/host/status_data1.txt`
- Create: `tests/fixtures/contracts/host/service_states.txt`
- Create: `tests/unit/tools/test_ssh_transport.py`
- Create: `tests/unit/tools/adapters/test_host.py`

- [ ] **Step 1：写 SSH 安全策略测试**

验证：

- `known_hosts` 缺失时拒绝连接，错误 `tool.configuration`。
- 使用 `RejectPolicy`，不得使用 `AutoAddPolicy`。
- 认证失败映射 `tool.authentication_failed`。
- 命令只能从 `SshCommandId` 枚举映射。
- stdout 与 stderr 合计超过字节上限时关闭 channel 并失败。
- 日志中不出现密码、私钥路径内容或底层命令输出。

- [ ] **Step 2：固定主机命令**

只允许代码中以下命令 ID：

```python
HOST_STATUS_COMMANDS = {
    SshCommandId.HOST_UPTIME: ("uptime", "-p"),
    SshCommandId.HOST_MEMORY: ("free", "-b"),
    SshCommandId.HOST_FILESYSTEM: ("df", "-B1", "--output=source,size,used,avail,pcent,target"),
    SshCommandId.HOST_INODES: ("df", "-i", "--output=source,itotal,iused,iavail,ipcent,target"),
    SshCommandId.HOST_TIME: ("timedatectl", "show", "--property=NTPSynchronized", "--value"),
}
```

实现时使用安全参数拼接函数，只接受静态 token；不得把 `arguments` 直接拼到命令。

- [ ] **Step 3：写主机 Observation 测试**

输出：

```text
host_uptime_seconds
host_memory
host_filesystems
host_inodes
host_time_synchronized
```

文件系统最多保留 50 条，过滤伪文件系统，保留根目录及使用率最高项。

- [ ] **Step 4：写服务状态目录测试**

`ServiceName` 只允许：

```text
kafka, flink_jobmanager, flink_taskmanager, doris_fe, doris_be,
mysql, redis, collector, spring_api, ai_engine
```

systemd 服务使用固定 `systemctl is-active`；手工服务使用固定 `pgrep -f -- <静态指纹>` 和固定端口探测。PID 不进入稳定知识，只作为带时间戳 Observation value。

- [ ] **Step 5：验证并提交**

Run:

```bash
.venv/bin/pytest \
  tests/unit/tools/test_ssh_transport.py \
  tests/unit/tools/adapters/test_host.py -q
.venv/bin/ruff check src tests
.venv/bin/mypy src
git add src/datasentry/tools tests/fixtures/contracts/host tests/unit/tools
git diff --cached --check
git commit -m "feat: 接入主机与服务状态只读工具"
```

### Task 8：实现 Kafka Topic、Broker 和 Consumer Group 只读工具

**Files:**

- Create: `src/datasentry/tools/adapters/kafka.py`
- Create: `tests/fixtures/contracts/kafka/topics.txt`
- Create: `tests/fixtures/contracts/kafka/topic_describe.txt`
- Create: `tests/fixtures/contracts/kafka/offsets_first.txt`
- Create: `tests/fixtures/contracts/kafka/offsets_second.txt`
- Create: `tests/fixtures/contracts/kafka/group_missing.txt`
- Create: `tests/unit/tools/adapters/test_kafka.py`

- [ ] **Step 1：写 Topic 白名单测试**

允许 Topic：

```text
binance.trade.raw
binance.depth.raw
streamlake.whale.alert
```

允许 Group：

```text
flink-kline-group
flink-cep-group
flink-risk-group
```

任何包含空白、Shell 元字符或目录分隔符的值在执行 SSH 前以 `tool.invalid_arguments` 拒绝。

- [ ] **Step 2：写推进状态测试**

`get_kafka_topic` 通过固定 `kafka-get-offsets.sh` 在短间隔内采样两次末端 Offset：

```python
assert fact(observations, "topic_advancing").value is True
assert fact(observations, "topic_partition_end_offsets").value == {
    "0": 102,
    "1": 205,
}
```

采样间隔由 `ToolLimits.kafka_sample_interval_seconds` 控制，范围 1～5 秒；测试注入无等待 sleeper。

- [ ] **Step 3：写 Consumer Group 不可见测试**

当 CLI 返回无 group：

```python
assert fact(observations, "consumer_group_visibility").value == {
    "group": "flink-kline-group",
    "state": "NOT_VISIBLE",
}
```

不得生成 `lag=0`，不得声称正常；unknown 摘要提示结合 Flink Source 指标和 Topic 最新 Offset。

- [ ] **Step 4：实现固定 Kafka 命令映射**

只允许 `/opt/kafka/bin` 下配置确认的：

```text
kafka-topics.sh --list
kafka-topics.sh --describe --topic <allowlisted>
kafka-get-offsets.sh --topic <allowlisted>
kafka-consumer-groups.sh --describe --group <allowlisted>
kafka-broker-api-versions.sh
```

Kafka 安装根目录来自目标配置，但必须是绝对路径且位于允许根 `/opt/kafka`。

- [ ] **Step 5：验证并提交**

Run:

```bash
.venv/bin/pytest tests/unit/tools/adapters/test_kafka.py -q
.venv/bin/ruff check src tests
.venv/bin/mypy src
git add src/datasentry/tools/adapters/kafka.py \
  tests/fixtures/contracts/kafka tests/unit/tools/adapters/test_kafka.py
git diff --cached --check
git commit -m "feat: 接入 Kafka 只读工具"
```

### Task 9：实现 Doris 数据新鲜度和 MySQL 受限查询

**Files:**

- Create: `src/datasentry/tools/transports/mysql.py`
- Create: `src/datasentry/tools/adapters/doris.py`
- Create: `src/datasentry/tools/adapters/mysql.py`
- Create: `tests/fixtures/contracts/doris/freshness_rows.json`
- Create: `tests/fixtures/contracts/mysql/risk_rules_rows.json`
- Create: `tests/unit/tools/test_mysql_transport.py`
- Create: `tests/unit/tools/adapters/test_doris.py`
- Create: `tests/unit/tools/adapters/test_mysql.py`

- [ ] **Step 1：写只读传输策略测试**

连接建立后立即执行：

```sql
SET SESSION TRANSACTION READ ONLY
```

传输类不公开 `execute(sql: str)`；只公开：

```python
def fetch_all(
    self,
    target: MySqlTarget,
    query: ReadOnlyQuery,
    parameters: tuple[object, ...],
) -> list[dict[str, JsonValue]]:
```

`ReadOnlyQuery` 来自代码目录。测试断言任何不以 `SELECT`、`SHOW` 或 `DESCRIBE` 开头的目录条目在构造时失败。

- [ ] **Step 2：固定 Doris 新鲜度查询**

目录只允许：

```text
kline_1min      -> MAX(open_time)
whale_alert     -> MAX(event_time)
risk_trigger    -> MAX(trigger_time)
ai_diagnosis    -> MAX(created_at)
```

表名和时间列不接受外部字符串插值。查询返回最新业务时间和数据库当前 UTC 时间，适配器计算：

```text
kline_latest_event_time
kline_freshness_seconds
```

空表返回 `latest_event_time=None` 和明确 unknown，不执行 `COUNT(*)`。

- [ ] **Step 3：固定 MySQL 样本查询**

只允许 `whale_thresholds` 与 `risk_rules`，默认 `LIMIT 20`，最大 100。只返回非秘密业务列；连接信息、密码和完整配置不进入 Observation。

- [ ] **Step 4：写时区与空值测试**

覆盖：

- 数据库返回带时区 datetime。
- 数据库返回 naive datetime 时按目标配置声明时区解释，再转换 UTC。
- 最新时间为 `NULL`。
- 当前时间早于业务时间，输出 `clock_skew_seconds` 而不是负 freshness。

- [ ] **Step 5：验证并提交**

Run:

```bash
.venv/bin/pytest \
  tests/unit/tools/test_mysql_transport.py \
  tests/unit/tools/adapters/test_doris.py \
  tests/unit/tools/adapters/test_mysql.py -q
.venv/bin/ruff check src tests
.venv/bin/mypy src
git add src/datasentry/tools tests/fixtures/contracts/doris \
  tests/fixtures/contracts/mysql tests/unit/tools
git diff --cached --check
git commit -m "feat: 接入 Doris 与 MySQL 受限查询"
```

### Task 10：实现 Redis 受限查询

**Files:**

- Create: `src/datasentry/tools/transports/redis.py`
- Create: `src/datasentry/tools/adapters/redis.py`
- Create: `tests/fixtures/contracts/redis/info.json`
- Create: `tests/fixtures/contracts/redis/key_sample.json`
- Create: `tests/unit/tools/test_redis_transport.py`
- Create: `tests/unit/tools/adapters/test_redis.py`

- [ ] **Step 1：写命令边界测试**

传输只暴露：

```python
info()
dbsize()
scan(cursor, match, count)
type(key)
ttl(key)
get(key)
hscan(key, cursor, count)
sscan(key, cursor, count)
zscan(key, cursor, count)
```

没有 `execute_command` 公共入口。测试使用 spy 断言从不调用 `KEYS`。

- [ ] **Step 2：写 Pattern 和限制测试**

只允许：

```text
risk:blacklist:*
```

`limit` 默认 20、最大 100；单个字符串值最多 2 KiB；Hash/Set/ZSet 每个 Key 最多 20 项；最多扫描 10 个 cursor 批次。

- [ ] **Step 3：写 Observation 测试**

输出：

```text
redis_info
redis_dbsize
redis_key_sample
redis_key_ttl
```

值先脱敏再进入 Observation。二进制或无法 UTF-8 解码的值只返回类型和字节数。

- [ ] **Step 4：验证并提交**

Run:

```bash
.venv/bin/pytest \
  tests/unit/tools/test_redis_transport.py \
  tests/unit/tools/adapters/test_redis.py -q
.venv/bin/ruff check src tests
.venv/bin/mypy src
git add src/datasentry/tools tests/fixtures/contracts/redis tests/unit/tools
git diff --cached --check
git commit -m "feat: 接入 Redis 受限只读工具"
```

### Task 11：实现有限日志工具

**Files:**

- Create: `src/datasentry/tools/adapters/logs.py`
- Create: `tests/fixtures/contracts/logs/spring_recent.log`
- Create: `tests/fixtures/contracts/logs/ai_recent.log`
- Create: `tests/unit/tools/adapters/test_logs.py`

- [ ] **Step 1：写日志源白名单测试**

日志源只能来自 `TargetCatalog.log_sources`，类型为：

```text
journal
file
```

`journal` 只接受目录中登记的 unit；`file` 只接受目录中登记的绝对路径。CLI 参数只传组件 alias，不能传 unit 或 path。

- [ ] **Step 2：写边界和脱敏测试**

覆盖：

- `lines > 200` 拒绝。
- `minutes > 30` 拒绝。
- 输出超过字节上限时失败，不保存半截秘密。
- password、Bearer Token、Cookie、AK/SK、JDBC URL 用户信息和 PEM 区块被遮蔽。
- ANSI 控制字符和不可打印字符被清理。

- [ ] **Step 3：固定日志命令**

只允许：

```text
journalctl --no-pager --utc --since "-<minutes> minutes" -n <lines> -u <fixed-unit>
tail -n <lines> -- <fixed-path>
```

`minutes` 和 `lines` 先转为受限整数；unit/path 来自已校验目录。不得支持 `grep` 自由表达式。

- [ ] **Step 4：输出日志 Observation**

```python
Observation(
    inspection_id=inspection_id,
    component=component,
    metric_or_fact="recent_logs",
    value={
        "lines": redacted_lines,
        "line_count": len(redacted_lines),
        "window_minutes": minutes,
        "truncated": False,
    },
    source="ssh_limited_logs",
    target=component,
    observed_at=clock(),
)
```

- [ ] **Step 5：验证并提交**

Run:

```bash
.venv/bin/pytest tests/unit/tools/adapters/test_logs.py -q
.venv/bin/ruff check src tests
.venv/bin/mypy src
git add src/datasentry/tools/adapters/logs.py \
  tests/fixtures/contracts/logs tests/unit/tools/adapters/test_logs.py
git diff --cached --check
git commit -m "feat: 增加有限日志只读工具"
```

### Task 12：实现确定性工具计划、采集器和真实诊断服务

**Files:**

- Create: `src/datasentry/tools/planner.py`
- Create: `src/datasentry/tools/collector.py`
- Create: `src/datasentry/tools/service.py`
- Modify: `src/datasentry/diagnosis/service.py`
- Create: `tests/unit/tools/test_planner.py`
- Create: `tests/unit/tools/test_collector.py`
- Create: `tests/unit/tools/test_live_service.py`

- [ ] **Step 1：写 Kline 工具计划测试**

```python
def test_planner_builds_kline_readonly_calls() -> None:
    prepared = prepared_diagnosis(
        question_type=QuestionType.DATA_STALE,
        node_ids=(
            "collector",
            "kafka.binance.trade.raw",
            "flink.kline",
            "doris.kline_1min",
            "api.kline.latest",
        ),
    )

    calls = ReadOnlyInspectionPlanner().plan(prepared)

    assert [call.name for call in calls] == [
        ToolName.GET_HOST_STATUS,
        ToolName.GET_SERVICE_STATUS,
        ToolName.GET_FLINK_JOBS,
        ToolName.GET_FLINK_JOB,
        ToolName.GET_FLINK_CHECKPOINTS,
        ToolName.GET_FLINK_BACKPRESSURE,
        ToolName.GET_KAFKA_TOPIC,
        ToolName.GET_DORIS_TABLE_FRESHNESS,
        ToolName.GET_API_HEALTH,
    ]
```

路由与计划固定映射，不由 LLM 生成。

- [ ] **Step 2：写其他问题类型计划测试**

- `component_down`：目标主机状态、服务状态、对应 API 健康；服务明确失败时追加有限日志。
- `latency_backpressure`：Flink Job、Checkpoint、反压、Kafka Topic、Doris freshness、主机资源。
- `configuration`：M2 不读取完整环境变量；只查询服务状态、已允许的只读表和 API 探针，并产生“生效配置来源尚未接入安全探针”的 unknown。

未识别组件时返回 `tool.plan_unsupported`，不扩大为全系统扫描。

- [ ] **Step 3：写局部失败采集测试**

```python
def test_collector_continues_after_one_tool_failure() -> None:
    result = collector_with_outcomes(
        failed(ToolName.GET_KAFKA_TOPIC, "tool.timeout"),
        succeeded(ToolName.GET_FLINK_JOBS, [flink_observation()]),
    ).collect("inspection-1", calls())

    assert result.observations == [flink_observation()]
    assert result.unknowns == [
        "工具 get_kafka_topic 查询 kafka:binance.trade.raw 失败（tool.timeout）"
    ]
```

- [ ] **Step 4：拆分 DiagnosisService 准备与完成阶段**

新增：

```python
class PreparedDiagnosis(DomainModel):
    inspection: Inspection
    route: RouteMatch
    knowledge: list[KnowledgeReference]
    lineage_checkpoints: list[LineageNode]


def prepare(self, question: str) -> PreparedDiagnosis:
    """完成路由、知识和血缘准备，但不访问生产工具。"""


def complete(
    self,
    prepared: PreparedDiagnosis,
    observations: list[Observation],
    collection_unknowns: tuple[str, ...] = (),
) -> DiagnosisResult:
    """运行规则并原子完成已启动的 Inspection。"""
```

现有 `diagnose()` 调用 `prepare()`、`start_inspection()`、`complete()`，保持 M1 测试和 CLI 兼容。

- [ ] **Step 5：实现 LiveInspectionService**

执行顺序：

1. `prepared = diagnosis.prepare(question)`。
2. `repository.start_inspection(prepared.inspection)`。
3. `calls = planner.plan(prepared)`。
4. `collection = collector.collect(inspection_id, calls)`。
5. `diagnosis.complete(prepared, collection.observations, tuple(collection.unknowns))`。
6. 读取 `list_tool_invocations()` 并返回。
7. 未预期异常时将 Inspection 标记 `failed`。

- [ ] **Step 6：验证服务层**

Run:

```bash
.venv/bin/pytest \
  tests/unit/tools/test_planner.py \
  tests/unit/tools/test_collector.py \
  tests/unit/tools/test_live_service.py \
  tests/unit/diagnosis/test_service.py -q
.venv/bin/ruff check src tests
.venv/bin/mypy src
```

Expected: 全部退出码为 `0`。

- [ ] **Step 7：提交编排检查点**

```bash
git add src/datasentry/diagnosis src/datasentry/tools tests/unit
git diff --cached --check
git commit -m "feat: 增加真实只读巡检编排"
```

### Task 13：增加真实巡检 CLI 和端到端模拟场景

**Files:**

- Modify: `src/datasentry/cli/app.py`
- Create: `tests/integration/tools/test_contract_fixtures.py`
- Create: `tests/scenarios/test_cli_real_readonly_inspection.py`

- [ ] **Step 1：写 CLI 帮助和参数测试**

```python
def test_inspection_run_help_is_chinese() -> None:
    result = runner.invoke(app, ["inspection", "run", "--help"])

    assert result.exit_code == 0
    assert "执行真实只读巡检" in result.stdout
    assert "目标配置 TOML" in result.stdout
```

参数：

```text
--question
--targets-file
--knowledge-root
--database-path
```

不提供 `--command`、`--sql`、`--url`、`--log-path`、`--redis-pattern`。

- [ ] **Step 2：写成功场景**

使用 fake HTTP transport、fake SSH transport、fake MySQL transport 和 fake Redis transport 注入 CLI service factory。断言：

```python
assert payload["route"]["question_type"] == "data_stale"
assert payload["aggregate"]["findings"][0]["claim"] == "K线链路停在 Flink 计算层"
assert len(payload["tool_invocations"]) == 9
assert {item["status"] for item in payload["tool_invocations"]} == {"succeeded"}
```

- [ ] **Step 3：写局部失败场景**

Kafka fake transport 抛 `tool.timeout`，其他组件成功。断言：

```python
assert result.exit_code == 0
assert any(
    "get_kafka_topic" in item
    for item in payload["aggregate"]["findings"][0]["unknowns"]
)
assert payload["aggregate"]["inspection"]["status"] == "completed"
```

- [ ] **Step 4：写秘密不泄露场景**

fixture 中植入：

```text
password=super-secret
Authorization: Bearer token-value
http://user:pass@example.test
-----BEGIN PRIVATE KEY-----
```

检查 stdout、stderr、SQLite `observations`、`findings`、`tool_invocations` 均不包含这些原文。

- [ ] **Step 5：实现 CLI 依赖装配**

将生产装配拆为可测试函数：

```python
def build_live_inspection_service(
    *,
    repository: Repository,
    targets: TargetCatalog,
    knowledge_root: Path,
) -> LiveInspectionService:
    """构造固定工具注册表和真实巡检服务。"""
```

CLI 只负责加载配置、打开 Repository、调用服务和输出 JSON。

- [ ] **Step 6：验证契约和场景**

Run:

```bash
.venv/bin/pytest \
  tests/integration/tools/test_contract_fixtures.py \
  tests/scenarios/test_cli_real_readonly_inspection.py -q
.venv/bin/ruff check src tests
.venv/bin/mypy src
```

Expected: 全部退出码为 `0`。

- [ ] **Step 7：提交 CLI 检查点**

```bash
git add src/datasentry/cli src/datasentry/tools \
  tests/integration/tools tests/scenarios/test_cli_real_readonly_inspection.py
git diff --cached --check
git commit -m "feat: 增加真实只读巡检 CLI"
```

### Task 14：文档、全量验证和生产只读影子验收

**Files:**

- Modify: `README.md`
- Modify: `docs/PROJECT_STATUS.md`
- Modify: `knowledge/09-agent-integration.md` only if implemented tool names or limits differ from current specification

- [ ] **Step 1：更新 README**

记录：

- M2 真实只读范围。
- `targets.example.toml` 复制方式。
- 只读账号和 SSH known_hosts 要求。
- 秘密环境变量只写名称，不写值。
- `inspection run` 示例。
- 工具失败如何显示 unknown。
- 明确禁止项。

- [ ] **Step 2：更新项目状态**

完成自动测试后，将 M2 状态写为“代码完成，等待生产只读影子验收”；只有现场成功后才写“已完成”。同步记录：

- 是否取得只读账号。
- 哪些适配器已现场验证。
- 未现场验证项。
- Kafka Consumer Group、日志路径、Doris/Flink 配置的新发现。
- 任何范围调整或安全例外。

- [ ] **Step 3：运行全量质量检查**

Run:

```bash
.venv/bin/ruff format --check .
.venv/bin/ruff check .
.venv/bin/mypy src
.venv/bin/pytest tests -q -W error::ResourceWarning \
  --cov=datasentry \
  --cov-report=term-missing \
  --cov-fail-under=90
```

Expected: 全部退出码为 `0`，覆盖率不低于 90%。

- [ ] **Step 4：运行本地秘密检查**

Run:

```bash
git diff --check
git grep -nEi \
  '(password|passwd|secret|token|access[_-]?key|secret[_-]?key|BEGIN .*PRIVATE KEY)' \
  -- ':!docs/superpowers/plans/2026-06-25-m2-real-readonly-tools.md' \
  ':!tests/fixtures/contracts/**'
```

Expected: 每个命中均为占位符、字段名、脱敏规则或测试数据；不存在真实秘密。若安装了 gitleaks，再运行：

```bash
gitleaks detect --no-banner --redact
```

- [ ] **Step 5：提交自动化完成检查点**

```bash
git add README.md docs/PROJECT_STATUS.md knowledge/09-agent-integration.md
git diff --cached --check
git commit -m "docs: 更新 M2 只读巡检说明"
```

- [ ] **Step 6：准备生产目标文件**

在不提交 Git 的 `config/targets.toml` 中填写真实目标；由用户在运行环境设置只读凭据。确认：

- SSH 账号无 sudo 和写权限。
- Doris/MySQL 账号只有 `SELECT`、`SHOW`、`DESCRIBE`。
- Redis ACL 只允许计划中的只读命令。
- Flink/API 只允许内网访问。
- known_hosts 已由可信渠道预置。

- [ ] **Step 7：先执行单工具影子验证**

按总体设计顺序逐项验证：

```text
Flink REST
→ Spring API / AI Engine
→ 主机状态
→ Kafka
→ Doris
→ Redis / MySQL
→ 有限日志
```

每项记录成功、稳定错误码、耗时、输出大小和脱敏结果。任何工具出现写操作、权限超界、输出秘密或无边界扫描迹象，立即停止现场验收。

- [ ] **Step 8：执行端到端只读巡检**

Run:

```bash
datasentry inspection run \
  --question "为什么K线不更新" \
  --targets-file config/targets.toml \
  --knowledge-root knowledge \
  --database-path var/datasentry-m2-shadow.db
```

Expected:

- 退出码 `0`。
- Inspection 为 `completed`。
- 工具调用均有审计。
- 成功工具 Observation 带现场时间和来源。
- 失败工具形成 unknown，不导致内部错误。
- 没有任何生产写操作。

- [ ] **Step 9：读回并核对审计**

Run:

```bash
datasentry inspection show INSPECTION_ID \
  --database-path var/datasentry-m2-shadow.db
```

使用 SQLite 只读查询或后续 CLI 审计子命令确认 `tool_invocations` 与本次巡检一致。手工检查 JSON 和结构化日志中无秘密。

- [ ] **Step 10：同步最终状态与提交**

现场验收通过后，将 `docs/PROJECT_STATUS.md` 中：

- 当前阶段更新为 M2 已完成。
- 下一里程碑更新为 M3 监控、看板与通知详细计划。
- 记录现场验证日期、已验证工具和剩余未知项。

提交：

```bash
git add docs/PROJECT_STATUS.md
git diff --cached --check
git commit -m "docs: 记录 M2 生产只读影子验收"
```

- [ ] **Step 11：推送前同步远端**

Run:

```bash
git fetch origin
git log --oneline --left-right --cherry-pick origin/main...HEAD
```

如 `origin/main` 有新提交，停止并评估 rebase/merge；不得覆盖远端。

- [ ] **Step 12：推送功能分支并创建 PR**

Run:

```bash
git push -u origin feat/m2-real-readonly-tools
```

PR 描述必须包含：

- 改动摘要。
- 全量验证结果和覆盖率。
- 生产影子验收结果。
- 未验证项。
- 安全边界与明确不包含项。

未经用户明确批准，不合并 PR、不删除远端分支。

## 6. 测试矩阵

| 层级 | 必测内容 |
|---|---|
| 单元 | 参数枚举、TOML 校验、秘密引用、脱敏、输出限制、超时分类、重试次数、固定命令/查询目录 |
| 契约 | Flink REST、API、Kafka CLI、Doris/MySQL、Redis 和日志脱敏 fixture 的解析 |
| 存储集成 | Schema 2、工具审计读回、Inspection 原子完成、失败状态、外键与排序 |
| 工具集成 | fake HTTP/SSH/MySQL/Redis 传输组合，验证适配器只调用允许方法 |
| CLI 场景 | Kline 成功、Kafka 超时降级、Flink Job 缺失、API 健康但读探针失败、秘密不泄露 |
| 安全 | 参数注入、Shell 元字符、非法 SQL 目录、Redis KEYS 不可达、日志路径逃逸、重定向换 host、输出超限 |
| 现场 | 每个工具单独影子验证、端到端 Kline 巡检、审计与脱敏人工复核 |

## 7. 计划完成后的稳定接口

M2 完成后，M3/M4 只能依赖以下稳定边界：

- `ToolGateway.execute(inspection_id, ToolCall) -> ToolOutcome`
- `ReadOnlyInspectionPlanner.plan(PreparedDiagnosis) -> tuple[ToolCall, ...]`
- `InspectionCollector.collect(...) -> CollectionResult`
- `LiveInspectionService.run(question) -> LiveInspectionResult`
- 标准 `Observation` 和现有 `DiagnosisService`
- Repository 的 Inspection 生命周期与 `ToolInvocation` 审计

Prometheus、FastAPI、LLM 和 Web 不应绕过这些边界直接访问 SSH、数据库、Redis 或生产 HTTP 接口。

## 8. 实施中必须停止并升级给用户的情况

- 真实目标要求关闭 SSH host key 校验。
- 只能获得具备写权限或 sudo 的账号，无法建立只读账号。
- Doris/MySQL 无法限制为只读。
- Redis 无法通过 ACL 限制命令。
- 真实 API 必须通过公网或跳过 TLS/身份校验访问。
- 工具必须读取完整环境变量、`.env`、Shell History、私钥内容或云 Metadata 才能工作。
- 需要执行未审计 `/root/bin` 脚本才能取得状态。
- 生产响应包含无法可靠脱敏的秘密结构。
- 现场发现总体架构或知识库中的组件路径、端口、表、字段或 Job 名与实际不一致，且会改变工具契约。

出现以上情况时，不扩大权限、不临时放开自由命令；更新 `docs/PROJECT_STATUS.md` 记录阻塞并请求用户决定。
