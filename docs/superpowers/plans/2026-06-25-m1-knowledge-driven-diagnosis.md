# DataSentry M1 知识驱动诊断实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不连接生产系统、不依赖 LLM 的前提下，使 DataSentry 能根据问题加载 1～3 份相关知识、构建 StreamLake 显式检查链路，并依据模拟 Observation 生成可重复、可持久化的证据化 Finding。

**Architecture:** 解析 `knowledge/INDEX.md` 得到受控主题目录，使用显式关键词策略识别“数据不更新、组件宕机、延迟/反压、配置问题”四类问题；以代码内稳定目录构建 Collector → Kafka → Flink → Doris/Redis 血缘图；诊断规则实现为无 I/O 的纯函数，编排服务负责知识、血缘、规则和 Repository 的组合。M1 CLI 只接受本地 JSON 模拟 Observation，真实 Flink、Kafka、Doris、Redis、MySQL、主机和日志查询全部留到 M2。

**Tech Stack:** Python 3.12、Pydantic 2、Typer、标准库 `pathlib/json/re`、SQLite Repository、pytest、Ruff、mypy

---

## 1. 范围与完成定义

### 1.1 M1 必须交付

- 解析 `knowledge/INDEX.md` 的“文档地图”和“快速路由”表。
- 校验知识路径不能逃逸 `knowledge/` 根目录，缺失文档、重复编号和非法索引应返回稳定安全错误。
- 将问题确定性路由为：
  - `data_stale`
  - `component_down`
  - `latency_backpressure`
  - `configuration`
- 每次加载 1～3 份主题文档；不默认加载全部知识库。
- 建立 Collector、Kafka Topic、三个 Flink Job、MySQL 规则表、Doris 表、Redis Key 和 Spring API 的显式血缘图。
- 为 Kline、Whale、Risk 三条链路返回有序检查路径。
- 实现首批四条确定性规则：
  - Kafka 原始 Topic 推进、Kline Job 缺失、Doris K 线停止推进。
  - 预期组件明确未运行。
  - Flink Job 存在高反压并连续 Checkpoint 失败。
  - 配置实际来源或生效值与预期不一致。
- 历史知识只作为 `KnowledgeReference` 输出，不直接生成 `confirmed` Evidence。
- 新增本地诊断 CLI：

```text
datasentry inspection diagnose \
  --question "为什么K线不更新" \
  --observations-file tests/fixtures/diagnosis/kline_job_missing.json \
  --knowledge-root knowledge \
  --database-path /tmp/datasentry-m1.db
```

- 诊断结果继续写入 M0 SQLite 表并可通过 `inspection show` 读回。
- 单元测试、知识集成测试和 CLI 场景测试覆盖成功、证据不足、历史知识隔离和安全失败路径。

### 1.2 M1 明确不做

- 不连接 SSH、Flink REST、Kafka CLI/API、Doris、Redis、MySQL、Spring API、Prometheus 或日志；这些属于 M2。
- 不引入 RAG、Embedding、向量数据库、全文检索框架或 LLM。
- 不从自由文本自动推导任意新血缘；M1 血缘必须显式、可审查、可测试。
- 不把 `knowledge/07-runtime-baseline-2026-06-25.md` 的历史快照当作当前状态。
- 不实现 Incident 自动聚合、FastAPI、Web、告警通知、审批、Runbook 或任何写操作。
- 不修改 M0 数据库 schema；知识引用和路由上下文只进入 CLI 返回值与 Inspection 的 `scope/summary`，Observation 和 Finding 沿用现有表。

### 1.3 验收场景

使用固定场景 `tests/fixtures/diagnosis/kline_job_missing.json` 执行：

```bash
datasentry db upgrade --database-path /tmp/datasentry-m1.db
datasentry inspection diagnose \
  --question "为什么K线不更新" \
  --observations-file tests/fixtures/diagnosis/kline_job_missing.json \
  --knowledge-root knowledge \
  --database-path /tmp/datasentry-m1.db
```

预期 JSON 满足：

- `route.question_type == "data_stale"`。
- `knowledge` 只包含 `03-jobs-and-lineage.md` 和 `04-configuration-and-reliability.md`，数量不超过 3。
- `lineage_checkpoints` 依次包含 Collector、`binance.trade.raw`、Kline Job、Doris `kline_1min` 和 Spring API Kline 接口。
- 三条模拟 Observation 被原样持久化。
- Finding 的结论为“K线链路停在 Flink 计算层”，状态为 `inferred`。
- Finding 只引用带现场时间、来源和目标的模拟 Observation；Markdown 内容只出现在 `knowledge` 引用中。
- `inspection show` 读回的 Inspection、Observation 和 Finding 与诊断结果中的持久化聚合一致。

## 2. 设计决策

### 2.1 知识索引是路由入口，不是实时事实源

M1 解析现有 Markdown 表格获得主题文件、摘要、典型问题和推荐组合。主题正文以完整文本加载，供后续 API/LLM 展示或总结，但规则不得把正文句子直接转成当前 Evidence。

### 2.2 结构化血缘显式维护

Markdown 适合人阅读，不适合在每次诊断时通过启发式文本抽取重建拓扑。M1 在 `catalog.py` 中维护与 `knowledge/03-jobs-and-lineage.md` 对应的稳定节点和边；知识变化时必须同步更新目录测试。

### 2.3 路由与规则保持确定性

- 路由按明确关键词优先级匹配，不调用模型。
- 同一输入问题和 Observation 必须产生相同的问题类型、知识组合、检查链路和 Finding 语义。
- 规则只读取标准化 Observation，不执行 I/O。
- 证据不足时返回 `unknown` Finding，不猜测当前状态。

### 2.4 M2 的替换边界

`DiagnosisService` 接受 `list[Observation]`。M1 由 JSON fixture 提供这些 Observation；M2 的白名单工具只需产出相同领域模型，无需改写知识路由、血缘遍历或规则接口。

## 3. 文件结构与职责

```text
src/datasentry/
├── knowledge/
│   ├── __init__.py          # 公共导出
│   ├── models.py            # KnowledgeTopic、KnowledgeReference、RouteMatch
│   ├── index.py             # INDEX Markdown 表格解析与安全校验
│   ├── router.py            # 四类问题的确定性路由
│   ├── lineage.py           # 血缘节点、边、图遍历
│   └── catalog.py           # StreamLake 稳定血缘目录和诊断检查路径
├── diagnosis/
│   ├── __init__.py          # 公共导出
│   ├── rules.py             # Rule Protocol、RuleContext、规则结果
│   ├── builtin_rules.py     # M1 四条确定性规则
│   └── service.py           # 路由、知识、血缘、规则、持久化编排
└── cli/
    └── app.py               # 新增 inspection diagnose
tests/
├── fixtures/diagnosis/
│   ├── kline_job_missing.json
│   ├── insufficient_evidence.json
│   ├── component_down.json
│   ├── flink_backpressure.json
│   └── configuration_mismatch.json
├── unit/knowledge/
│   ├── test_index.py
│   ├── test_router.py
│   └── test_lineage.py
├── unit/diagnosis/
│   ├── test_builtin_rules.py
│   └── test_service.py
├── integration/knowledge/
│   └── test_repository_knowledge.py
└── scenarios/
    └── test_cli_knowledge_diagnosis.py
```

## 4. 核心契约

### 4.1 知识模型

```python
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class QuestionType(StrEnum):
    DATA_STALE = "data_stale"
    COMPONENT_DOWN = "component_down"
    LATENCY_BACKPRESSURE = "latency_backpressure"
    CONFIGURATION = "configuration"


class KnowledgeTopic(BaseModel):
    model_config = ConfigDict(frozen=True)

    topic_id: str = Field(pattern=r"^\d{2}$")
    path: Path
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    typical_questions: tuple[str, ...] = ()
    historical: bool = False


class KnowledgeReference(BaseModel):
    model_config = ConfigDict(frozen=True)

    topic_id: str
    path: str
    title: str
    historical: bool


class RouteMatch(BaseModel):
    model_config = ConfigDict(frozen=True)

    question_type: QuestionType
    required_topic_ids: tuple[str, ...]
    optional_topic_ids: tuple[str, ...] = ()
    matched_keywords: tuple[str, ...]
```

### 4.2 血缘模型

```python
class LineageNodeKind(StrEnum):
    EXTERNAL = "external"
    SERVICE = "service"
    TOPIC = "topic"
    JOB = "job"
    TABLE = "table"
    KEY_PATTERN = "key_pattern"
    API = "api"


class LineageNode(BaseModel):
    model_config = ConfigDict(frozen=True)

    node_id: str
    kind: LineageNodeKind
    component: str
    label: str


class LineageEdge(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_id: str
    target_id: str
    relation: str


class LineageGraph:
    def __init__(self, nodes: tuple[LineageNode, ...], edges: tuple[LineageEdge, ...]) -> None:
        """校验并保存有向血缘图。"""
        raise NotImplementedError

    def node(self, node_id: str) -> LineageNode:
        """按稳定 ID 返回节点。"""
        raise NotImplementedError

    def shortest_path(self, source_id: str, target_id: str) -> tuple[LineageNode, ...]:
        """按边插入顺序返回最短检查路径。"""
        raise NotImplementedError
```

### 4.3 规则和编排接口

```python
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RuleContext:
    inspection_id: str
    question_type: QuestionType
    observations: tuple[Observation, ...]
    lineage_checkpoints: tuple[LineageNode, ...]
    created_at: datetime

    def find(self, component: str, metric_or_fact: str) -> Observation | None:
        """返回时间最新的匹配 Observation。"""
        raise NotImplementedError


class DiagnosisRule(Protocol):
    rule_id: str
    supported_question_types: frozenset[QuestionType]

    def evaluate(self, context: RuleContext) -> Finding | None:
        """对标准化 Observation 执行纯函数规则。"""
        raise NotImplementedError


class DiagnosisResult(BaseModel):
    route: RouteMatch
    knowledge: list[KnowledgeReference]
    lineage_checkpoints: list[LineageNode]
    aggregate: InspectionAggregate


class DiagnosisService:
    def __init__(
        self,
        repository: Repository,
        knowledge_index: KnowledgeIndex,
        router: KnowledgeRouter,
        lineage_graph: LineageGraph,
        rules: Sequence[DiagnosisRule],
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        """保存编排依赖，不执行 I/O。"""
        raise NotImplementedError

    def diagnose(self, question: str, observations: list[Observation]) -> DiagnosisResult:
        """完成一次本地知识驱动诊断并持久化。"""
        raise NotImplementedError
```

## 5. 分任务实施步骤

### Task 1：建立知识模型与安全索引解析器

**Files:**

- Create: `src/datasentry/knowledge/__init__.py`
- Create: `src/datasentry/knowledge/models.py`
- Create: `src/datasentry/knowledge/index.py`
- Create: `tests/unit/knowledge/test_index.py`

- [ ] **Step 1：先写 INDEX 解析成功测试**

```python
def test_index_parses_document_map_and_routes(tmp_path: Path) -> None:
    root = write_knowledge_tree(tmp_path)

    index = KnowledgeIndex.load(root)

    assert index.topic("03").path == root / "03-jobs-and-lineage.md"
    assert index.topic("03").title == "任务、Topic与数据血缘"
    assert index.topic("07").historical is True
    assert index.route("数据延迟/断流").required_topic_ids == ("03",)
    assert index.route("数据延迟/断流").optional_topic_ids == ("04", "07", "08")
```

测试辅助函数写入最小但完整的“文档地图”和“快速路由”Markdown 表，避免单元测试依赖仓库根目录。

- [ ] **Step 2：写安全失败测试**

```python
@pytest.mark.parametrize(
    ("filename", "code"),
    [
        ("../outside.md", "knowledge.path_outside_root"),
        ("missing.md", "knowledge.topic_missing"),
    ],
)
def test_index_rejects_unsafe_or_missing_topic(
    tmp_path: Path,
    filename: str,
    code: str,
) -> None:
    root = write_knowledge_tree(tmp_path, topic_filename=filename)

    with pytest.raises(KnowledgeError) as raised:
        KnowledgeIndex.load(root)

    assert raised.value.code == code
```

另测重复 `topic_id`、缺少表头、路由引用不存在主题，错误码分别为：

```text
knowledge.duplicate_topic
knowledge.invalid_index
knowledge.route_topic_missing
```

- [ ] **Step 3：运行测试确认失败**

Run:

```bash
.venv/bin/pytest tests/unit/knowledge/test_index.py -q
```

Expected: FAIL，错误包含 `ModuleNotFoundError: No module named 'datasentry.knowledge'`。

- [ ] **Step 4：实现知识模型、错误和索引解析**

在 `src/datasentry/errors.py` 增加：

```python
class KnowledgeError(DataSentryError):
    """知识加载、校验或路由失败。"""
```

`KnowledgeIndex.load(root)` 必须：

1. `root.resolve()` 后读取 `INDEX.md`。
2. 只解析标题为 `## 文档地图` 与 `## 快速路由` 下方的 Markdown 表。
3. 从 `[03-jobs-and-lineage.md](03-jobs-and-lineage.md)` 提取文件名。
4. 通过 `candidate.resolve().is_relative_to(root)` 阻止路径逃逸。
5. 使用文件名前两位作为 `topic_id`。
6. 读取主题文档第一个 `# ` 标题作为 `KnowledgeTopic.title`。
7. 仅当文件名以 `07-runtime-baseline-` 开头时设置 `historical=True`。
8. 将“01、02、03”拆成有序 topic ID tuple；“对应组件主题文档”这类非编号说明不进入 topic ID。
9. 提供 `topic()`、`route()` 和 `load_topic_text()`；正文使用 UTF-8。

- [ ] **Step 5：验证索引测试**

Run:

```bash
.venv/bin/pytest tests/unit/knowledge/test_index.py -q
.venv/bin/ruff check src/datasentry/knowledge tests/unit/knowledge
.venv/bin/mypy src
```

Expected: 全部退出码为 `0`。

- [ ] **Step 6：提交知识索引边界**

```bash
git add src/datasentry/errors.py src/datasentry/knowledge tests/unit/knowledge
git diff --cached --check
git commit -m "feat: 增加知识索引解析"
```

### Task 2：实现四类问题的确定性知识路由

**Files:**

- Create: `src/datasentry/knowledge/router.py`
- Create: `tests/unit/knowledge/test_router.py`
- Modify: `src/datasentry/knowledge/__init__.py`

- [ ] **Step 1：写路由参数化测试**

```python
@pytest.mark.parametrize(
    ("question", "question_type", "required"),
    [
        ("为什么K线不更新", QuestionType.DATA_STALE, ("03", "04")),
        ("Collector是不是挂了", QuestionType.COMPONENT_DOWN, ("02", "06")),
        ("Flink反压很高而且Checkpoint失败", QuestionType.LATENCY_BACKPRESSURE, ("03", "04")),
        ("Whale阈值配置为什么没生效", QuestionType.CONFIGURATION, ("04", "03")),
    ],
)
def test_router_selects_question_type_and_topics(
    knowledge_index: KnowledgeIndex,
    question: str,
    question_type: QuestionType,
    required: tuple[str, ...],
) -> None:
    match = KnowledgeRouter(knowledge_index).route(question)

    assert match.question_type is question_type
    assert match.required_topic_ids == required
    assert 1 <= len(match.required_topic_ids + match.optional_topic_ids) <= 3
```

- [ ] **Step 2：写优先级和未知问题测试**

```python
def test_router_prefers_configuration_over_generic_failure_word(
    knowledge_index: KnowledgeIndex,
) -> None:
    match = KnowledgeRouter(knowledge_index).route("配置错误导致Job不更新吗")
    assert match.question_type is QuestionType.CONFIGURATION


def test_router_rejects_unclassified_question(knowledge_index: KnowledgeIndex) -> None:
    with pytest.raises(KnowledgeError) as raised:
        KnowledgeRouter(knowledge_index).route("给我讲个故事")

    assert raised.value.code == "knowledge.question_unclassified"
```

- [ ] **Step 3：运行测试确认失败**

Run:

```bash
.venv/bin/pytest tests/unit/knowledge/test_router.py -q
```

Expected: FAIL，错误包含无法导入 `KnowledgeRouter`。

- [ ] **Step 4：实现显式路由策略**

固定优先级和关键词：

```python
ROUTE_POLICIES = (
    RoutePolicy(
        question_type=QuestionType.CONFIGURATION,
        keywords=("配置", "参数", "环境变量", "没生效", "阈值"),
        required_topic_ids=("04", "03"),
        optional_topic_ids=("02",),
    ),
    RoutePolicy(
        question_type=QuestionType.LATENCY_BACKPRESSURE,
        keywords=("延迟", "反压", "backpressure", "checkpoint", "积压", "lag"),
        required_topic_ids=("03", "04"),
        optional_topic_ids=("08",),
    ),
    RoutePolicy(
        question_type=QuestionType.COMPONENT_DOWN,
        keywords=("宕机", "挂了", "没启动", "未运行", "连接不上", "不可用"),
        required_topic_ids=("02", "06"),
        optional_topic_ids=("08",),
    ),
    RoutePolicy(
        question_type=QuestionType.DATA_STALE,
        keywords=("不更新", "没数据", "断流", "新鲜度", "停止推进"),
        required_topic_ids=("03", "04"),
        optional_topic_ids=("02",),
    ),
)
```

路由器按策略顺序匹配，返回命中的全部关键词。普通问题只加载 `required_topic_ids`，`optional_topic_ids` 作为后续限定词的候选，不默认加载；最终实际加载列表去重并限制为 1～3 份。策略引用的 topic 必须存在于 `KnowledgeIndex`。

当问题包含“历史”“上次”或“基线”时，将 `07` 追加到 `required_topic_ids` 并将结果限制为 3 份，但 `07` 仍只作为 `historical` 知识引用，不参与当前事实确认。

- [ ] **Step 5：验证路由测试与静态检查**

Run:

```bash
.venv/bin/pytest tests/unit/knowledge/test_router.py -q
.venv/bin/ruff format --check src tests
.venv/bin/ruff check src tests
.venv/bin/mypy src
```

Expected: 全部退出码为 `0`。

- [ ] **Step 6：提交知识路由**

```bash
git add src/datasentry/knowledge tests/unit/knowledge/test_router.py
git diff --cached --check
git commit -m "feat: 增加确定性知识路由"
```

### Task 3：建立 StreamLake 显式血缘图与检查链路

**Files:**

- Create: `src/datasentry/knowledge/lineage.py`
- Create: `src/datasentry/knowledge/catalog.py`
- Create: `tests/unit/knowledge/test_lineage.py`
- Modify: `src/datasentry/knowledge/__init__.py`

- [ ] **Step 1：写 Kline、Whale、Risk 路径测试**

```python
def test_kline_check_path_is_ordered() -> None:
    graph = build_streamlake_lineage()

    path = graph.shortest_path("collector", "api.kline.latest")

    assert [node.node_id for node in path] == [
        "collector",
        "kafka.binance.trade.raw",
        "flink.kline",
        "doris.kline_1min",
        "api.kline.latest",
    ]


@pytest.mark.parametrize(
    ("target", "expected_tail"),
    [
        ("doris.whale_alert", ["flink.whale", "doris.whale_alert"]),
        ("kafka.streamlake.whale.alert", ["flink.whale", "kafka.streamlake.whale.alert"]),
        ("doris.risk_trigger", ["flink.risk", "doris.risk_trigger"]),
        ("redis.risk.blacklist", ["flink.risk", "redis.risk.blacklist"]),
    ],
)
def test_trade_lineage_reaches_expected_sink(
    target: str,
    expected_tail: list[str],
) -> None:
    path = build_streamlake_lineage().shortest_path("collector", target)
    assert [node.node_id for node in path][-2:] == expected_tail
```

- [ ] **Step 2：写图完整性和未知节点测试**

```python
def test_graph_rejects_edge_with_unknown_node() -> None:
    with pytest.raises(LineageError) as raised:
        LineageGraph(nodes=(), edges=(LineageEdge(source_id="a", target_id="b", relation="writes"),))
    assert raised.value.code == "lineage.unknown_node"


def test_missing_path_returns_safe_error() -> None:
    graph = build_streamlake_lineage()
    with pytest.raises(LineageError) as raised:
        graph.shortest_path("mysql.whale_thresholds", "redis.risk.blacklist")
    assert raised.value.code == "lineage.path_not_found"
```

- [ ] **Step 3：运行测试确认失败**

Run:

```bash
.venv/bin/pytest tests/unit/knowledge/test_lineage.py -q
```

Expected: FAIL，错误包含无法导入 `build_streamlake_lineage`。

- [ ] **Step 4：实现图和稳定目录**

在 `src/datasentry/errors.py` 增加：

```python
class LineageError(DataSentryError):
    """血缘目录或遍历失败。"""
```

`catalog.py` 至少声明以下节点：

```text
binance.websocket
collector
kafka.binance.trade.raw
flink.kline
flink.whale
flink.risk
mysql.whale_thresholds
mysql.risk_rules
doris.kline_1min
doris.whale_alert
kafka.streamlake.whale.alert
doris.risk_trigger
redis.risk.blacklist
api.kline.latest
```

边必须与 `knowledge/03-jobs-and-lineage.md` 一致。`LineageGraph.shortest_path()` 使用保持插入顺序的 BFS，返回包含起点和终点的 tuple；构造时校验节点 ID 唯一且每条边两端均存在。

- [ ] **Step 5：验证血缘测试与知识一致性**

Run:

```bash
.venv/bin/pytest tests/unit/knowledge/test_lineage.py -q
.venv/bin/ruff check src/datasentry/knowledge tests/unit/knowledge
.venv/bin/mypy src
```

Expected: 全部退出码为 `0`。

- [ ] **Step 6：提交血缘模型**

```bash
git add src/datasentry/errors.py src/datasentry/knowledge tests/unit/knowledge/test_lineage.py
git diff --cached --check
git commit -m "feat: 建立 StreamLake 显式血缘"
```

### Task 4：实现规则上下文和 Observation 证据转换

**Files:**

- Create: `src/datasentry/diagnosis/__init__.py`
- Create: `src/datasentry/diagnosis/rules.py`
- Create: `tests/unit/diagnosis/test_rules.py`

- [ ] **Step 1：写 Observation 查找和 Evidence 转换测试**

```python
def test_rule_context_finds_latest_matching_observation(observed_at: datetime) -> None:
    older = observation("flink", "job_state", {"state": "RUNNING"}, observed_at)
    newer = observation(
        "flink",
        "job_state",
        {"state": "MISSING"},
        observed_at + timedelta(minutes=1),
    )
    context = rule_context(older, newer)

    assert context.find("flink", "job_state") == newer


def test_observation_evidence_keeps_runtime_provenance(observed_at: datetime) -> None:
    item = observation("kafka", "topic_advancing", True, observed_at)

    evidence = evidence_from_observation(item, claim="Kafka 原始 Topic 仍在推进")

    assert evidence.status is EvidenceStatus.CONFIRMED
    assert evidence.source == item.source
    assert evidence.target == item.target
    assert evidence.observed_at == item.observed_at
```

- [ ] **Step 2：写历史来源隔离测试**

```python
def test_historical_observation_cannot_be_promoted_to_confirmed_evidence(
    observed_at: datetime,
) -> None:
    item = observation(
        "flink",
        "job_state",
        {"state": "RUNNING"},
        observed_at,
        source="knowledge:07-runtime-baseline-2026-06-25.md",
    )

    evidence = evidence_from_observation(item, claim="历史快照中的 Job 状态")

    assert evidence.status is EvidenceStatus.HISTORICAL
```

- [ ] **Step 3：运行测试确认失败**

Run:

```bash
.venv/bin/pytest tests/unit/diagnosis/test_rules.py -q
```

Expected: FAIL，错误包含 `ModuleNotFoundError: No module named 'datasentry.diagnosis'`。

- [ ] **Step 4：实现规则基础契约**

`RuleContext.find()` 按 `observed_at` 取最新匹配项。`evidence_from_observation()` 遵循：

```python
status = (
    EvidenceStatus.HISTORICAL
    if observation.source.startswith("knowledge:")
    else EvidenceStatus.CONFIRMED
)
```

Evidence `summary` 使用调用者提供的中文摘要，不直接 dump 无界 JSON。M1 fixture 的 `source` 固定为 `simulation_fixture`，明确它是测试输入而非生产事实。

- [ ] **Step 5：验证规则基础测试**

Run:

```bash
.venv/bin/pytest tests/unit/diagnosis/test_rules.py -q
.venv/bin/ruff check src/datasentry/diagnosis tests/unit/diagnosis
.venv/bin/mypy src
```

Expected: 全部退出码为 `0`。

- [ ] **Step 6：提交规则基础设施**

```bash
git add src/datasentry/diagnosis tests/unit/diagnosis/test_rules.py
git diff --cached --check
git commit -m "feat: 增加诊断规则基础契约"
```

### Task 5：实现首批四条确定性诊断规则

**Files:**

- Create: `src/datasentry/diagnosis/builtin_rules.py`
- Create: `tests/unit/diagnosis/test_builtin_rules.py`
- Modify: `src/datasentry/diagnosis/__init__.py`

- [ ] **Step 1：写 Kline 断流规则测试**

```python
def test_kline_rule_locates_break_at_flink(observed_at: datetime) -> None:
    context = rule_context(
        observation("kafka", "topic_advancing", True, observed_at),
        observation("flink", "kline_job_state", {"state": "MISSING"}, observed_at),
        observation("doris", "kline_freshness_seconds", 900, observed_at),
        question_type=QuestionType.DATA_STALE,
    )

    finding = KlineStalledAtFlinkRule().evaluate(context)

    assert finding is not None
    assert finding.status is EvidenceStatus.INFERRED
    assert finding.severity is Severity.CRITICAL
    assert finding.claim == "K线链路停在 Flink 计算层"
    assert len(finding.evidence) == 3
```

该规则仅在 `topic_advancing is True`、Job state 为 `MISSING/FAILED/CANCELED` 且新鲜度大于等于 300 秒时命中。

- [ ] **Step 2：写组件、反压和配置规则测试**

```python
def test_component_down_rule_reports_confirmed_absence() -> None:
    context = rule_context(
        observation("collector", "service_state", {"state": "NOT_RUNNING"}, NOW),
        question_type=QuestionType.COMPONENT_DOWN,
    )
    finding = ComponentDownRule().evaluate(context)
    assert finding is not None
    assert finding.status is EvidenceStatus.CONFIRMED
    assert finding.claim == "Collector 当前未运行"


def test_backpressure_rule_requires_high_pressure_and_checkpoint_failures() -> None:
    context = rule_context(
        observation("flink", "backpressure_level", "high", NOW),
        observation("flink", "checkpoint_consecutive_failures", 3, NOW),
        question_type=QuestionType.LATENCY_BACKPRESSURE,
    )
    finding = FlinkBackpressureRule().evaluate(context)
    assert finding is not None
    assert finding.status is EvidenceStatus.INFERRED


def test_configuration_rule_reports_effective_source_mismatch() -> None:
    context = rule_context(
        observation(
            "flink",
            "configuration_resolution",
            {"key": "WHALE_THRESHOLD", "expected_source": "mysql", "effective_source": "default"},
            NOW,
        ),
        question_type=QuestionType.CONFIGURATION,
    )
    finding = ConfigurationMismatchRule().evaluate(context)
    assert finding is not None
    assert finding.status is EvidenceStatus.CONFIRMED
```

- [ ] **Step 3：写证据不足测试**

```python
def test_kline_rule_returns_unknown_when_required_observation_is_missing() -> None:
    context = rule_context(
        observation("kafka", "topic_advancing", True, NOW),
        question_type=QuestionType.DATA_STALE,
    )

    finding = KlineStalledAtFlinkRule().evaluate(context)

    assert finding is not None
    assert finding.status is EvidenceStatus.UNKNOWN
    assert finding.unknowns == [
        "Kline Job 当前状态未知",
        "Doris kline_1min 数据新鲜度未知",
    ]
```

- [ ] **Step 4：运行测试确认失败**

Run:

```bash
.venv/bin/pytest tests/unit/diagnosis/test_builtin_rules.py -q
```

Expected: FAIL，错误包含无法导入 `KlineStalledAtFlinkRule`。

- [ ] **Step 5：实现四条规则**

每条规则必须声明稳定 `rule_id` 和支持的问题类型：

```text
data.kline_stalled_at_flink
component.not_running
flink.backpressure_with_checkpoint_failures
configuration.effective_value_mismatch
```

规则返回的 `Finding.inspection_id`、`created_at` 必须来自 `RuleContext`。规则不得读取文件、数据库、环境变量或网络。

- [ ] **Step 6：验证规则测试**

Run:

```bash
.venv/bin/pytest tests/unit/diagnosis/test_builtin_rules.py -q
.venv/bin/pytest tests/unit/diagnosis -q
.venv/bin/ruff check src/datasentry/diagnosis tests/unit/diagnosis
.venv/bin/mypy src
```

Expected: 全部退出码为 `0`。

- [ ] **Step 7：提交确定性规则**

```bash
git add src/datasentry/diagnosis tests/unit/diagnosis/test_builtin_rules.py
git diff --cached --check
git commit -m "feat: 增加首批确定性诊断规则"
```

### Task 6：实现诊断编排与 SQLite 持久化

**Files:**

- Create: `src/datasentry/diagnosis/service.py`
- Create: `tests/unit/diagnosis/test_service.py`
- Modify: `src/datasentry/diagnosis/__init__.py`

- [ ] **Step 1：写 Kline 诊断编排测试**

```python
def test_service_routes_loads_lineage_evaluates_and_persists(
    repository: SQLiteRepository,
    knowledge_index: KnowledgeIndex,
    observed_at: datetime,
) -> None:
    service = build_service(repository, knowledge_index, clock=lambda: observed_at)

    result = service.diagnose(
        "为什么K线不更新",
        kline_job_missing_observations(inspection_id="temporary"),
    )

    assert result.route.question_type is QuestionType.DATA_STALE
    assert [item.topic_id for item in result.knowledge] == ["03", "04"]
    assert [item.node_id for item in result.lineage_checkpoints] == [
        "collector",
        "kafka.binance.trade.raw",
        "flink.kline",
        "doris.kline_1min",
        "api.kline.latest",
    ]
    assert result.aggregate.findings[0].claim == "K线链路停在 Flink 计算层"
    assert repository.get_inspection(result.aggregate.inspection.id) == result.aggregate
```

- [ ] **Step 2：写 ID 归一化、历史隔离和失败原子性测试**

```python
def test_service_rebinds_input_observations_to_created_inspection(
    repository: SQLiteRepository,
    knowledge_index: KnowledgeIndex,
    observed_at: datetime,
) -> None:
    service = build_service(repository, knowledge_index, clock=lambda: observed_at)
    observations = kline_job_missing_observations(inspection_id="fixture")
    result = service.diagnose("为什么K线不更新", observations)
    inspection_id = result.aggregate.inspection.id
    assert {item.inspection_id for item in result.aggregate.observations} == {inspection_id}


def test_service_exposes_historical_topic_only_as_reference(
    repository: SQLiteRepository,
    knowledge_index: KnowledgeIndex,
    observed_at: datetime,
) -> None:
    service = build_service(repository, knowledge_index, clock=lambda: observed_at)
    observations = kline_job_missing_observations(inspection_id="fixture")
    result = service.diagnose("Kafka延迟是否比历史更高", observations)
    historical = [item for item in result.knowledge if item.historical]
    assert [item.topic_id for item in historical] == ["07"]
    assert all(item.path.endswith(".md") for item in historical)
    assert all(
        evidence.status is not EvidenceStatus.CONFIRMED
        for finding in result.aggregate.findings
        for evidence in finding.evidence
        if evidence.source.startswith("knowledge:")
    )


def test_service_does_not_persist_when_question_cannot_be_routed(
    knowledge_index: KnowledgeIndex,
    observed_at: datetime,
) -> None:
    repository = Mock(spec=Repository)
    service = build_service(
        repository,
        knowledge_index,
        clock=lambda: observed_at,
    )
    with pytest.raises(KnowledgeError):
        service.diagnose("给我讲个故事", [])
    repository.save_inspection.assert_not_called()
    repository.add_observation.assert_not_called()
    repository.add_finding.assert_not_called()
```

测试文件从 `unittest.mock` 导入 `Mock`，不要为生产 Repository 增加仅供测试的计数接口。

- [ ] **Step 3：运行测试确认失败**

Run:

```bash
.venv/bin/pytest tests/unit/diagnosis/test_service.py -q
```

Expected: FAIL，错误包含无法导入 `DiagnosisService`。

- [ ] **Step 4：实现编排顺序**

`diagnose()` 固定执行：

```text
校验问题非空
→ 路由问题
→ 加载最多3份知识引用与正文
→ 按问题和实体选择检查链路
→ 创建 RUNNING Inspection
→ 将输入 Observation 的 inspection_id 统一替换为新 ID
→ 执行支持当前 question_type 的规则
→ 若无规则产出，创建一个带系统 unknown Evidence 的 unknown Finding
→ 将 Inspection 更新为 COMPLETED
→ 保存 Inspection、Observation、Finding
→ 读回 InspectionAggregate
→ 返回 DiagnosisResult
```

M1 实体选择规则：

```python
if "k线" in normalized_question or "kline" in normalized_question:
    path = graph.shortest_path("collector", "api.kline.latest")
elif "巨鲸" in normalized_question or "whale" in normalized_question:
    path = graph.shortest_path("collector", "doris.whale_alert")
elif "风控" in normalized_question or "risk" in normalized_question:
    path = graph.shortest_path("collector", "redis.risk.blacklist")
else:
    path = ()
```

无规则产出时使用以下 Evidence，避免违反 `Finding.evidence` 至少一项的领域约束：

```python
Evidence(
    claim="当前 Observation 不足以形成确定性结论",
    status=EvidenceStatus.UNKNOWN,
    source="datasentry_diagnosis",
    target=None,
    observed_at=finished_at,
    summary="没有规则满足全部前置证据",
)
```

持久化沿用现有 Repository 方法，不新增 migration。若持久化中途失败，SQLite Repository 当前每次方法独立提交，M1 不承诺跨聚合事务；必须让错误向上返回且不得输出“诊断完成”。跨聚合事务作为后续 Repository Unit of Work 改进项记录在项目状态风险中。

- [ ] **Step 5：验证编排测试**

Run:

```bash
.venv/bin/pytest tests/unit/diagnosis/test_service.py -q
.venv/bin/pytest tests/unit/diagnosis tests/unit/knowledge -q
.venv/bin/ruff check src tests
.venv/bin/mypy src
```

Expected: 全部退出码为 `0`。

- [ ] **Step 6：提交诊断编排**

```bash
git add src/datasentry/diagnosis tests/unit/diagnosis/test_service.py
git diff --cached --check
git commit -m "feat: 编排知识驱动诊断"
```

### Task 7：接入真实仓库知识库并建立一致性测试

**Files:**

- Create: `tests/integration/knowledge/test_repository_knowledge.py`
- Modify: `src/datasentry/knowledge/catalog.py`（仅在测试发现文档与目录不一致时）

- [ ] **Step 1：写真实 INDEX 和主题加载测试**

```python
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_repository_knowledge_index_is_valid() -> None:
    index = KnowledgeIndex.load(REPOSITORY_ROOT / "knowledge")

    assert set(index.topic_ids()) == {f"{number:02d}" for number in range(1, 10)}
    assert index.topic("07").historical is True
    assert "Collector" in index.load_topic_text("03")
    assert "任意Shell" in index.load_topic_text("09").replace(" ", "")
```

- [ ] **Step 2：写索引、路由和血缘一致性测试**

```python
def test_repository_routes_reference_existing_topics() -> None:
    index = KnowledgeIndex.load(REPOSITORY_ROOT / "knowledge")
    for route in index.routes():
        for topic_id in route.required_topic_ids + route.optional_topic_ids:
            assert index.topic(topic_id).path.is_file()


def test_streamlake_catalog_contains_documented_primary_assets() -> None:
    graph = build_streamlake_lineage()
    documented = (REPOSITORY_ROOT / "knowledge/03-jobs-and-lineage.md").read_text()
    for name in (
        "binance.trade.raw",
        "KlineAggregationJob",
        "WhaleCepJob",
        "RiskControlJob",
        "kline_1min",
        "whale_alert",
        "risk_trigger",
        "risk:blacklist:{SYMBOL}",
    ):
        assert name in documented
    assert graph.node("flink.kline").label == "KlineAggregationJob"
```

- [ ] **Step 3：运行集成测试并修正目录差异**

Run:

```bash
.venv/bin/pytest tests/integration/knowledge/test_repository_knowledge.py -q
```

Expected: PASS；若失败，只能修正解析器或显式目录与已批准知识文档之间的真实不一致，不得放宽安全校验绕过问题。

- [ ] **Step 4：提交知识一致性测试**

```bash
git add src/datasentry/knowledge/catalog.py tests/integration/knowledge
git diff --cached --check
git commit -m "test: 校验知识库与血缘目录一致性"
```

### Task 8：新增模拟 Observation fixture 和诊断 CLI

**Files:**

- Create: `tests/fixtures/diagnosis/kline_job_missing.json`
- Create: `tests/fixtures/diagnosis/insufficient_evidence.json`
- Create: `tests/fixtures/diagnosis/component_down.json`
- Create: `tests/fixtures/diagnosis/flink_backpressure.json`
- Create: `tests/fixtures/diagnosis/configuration_mismatch.json`
- Create: `tests/scenarios/test_cli_knowledge_diagnosis.py`
- Modify: `src/datasentry/cli/app.py`

- [ ] **Step 1：创建 Kline fixture**

`tests/fixtures/diagnosis/kline_job_missing.json`：

```json
[
  {
    "inspection_id": "fixture",
    "component": "kafka",
    "metric_or_fact": "topic_advancing",
    "value": true,
    "source": "simulation_fixture",
    "target": "binance.trade.raw",
    "observed_at": "2026-06-25T12:00:00Z"
  },
  {
    "inspection_id": "fixture",
    "component": "flink",
    "metric_or_fact": "kline_job_state",
    "value": {"state": "MISSING"},
    "source": "simulation_fixture",
    "target": "streamlake-kline-aggregation",
    "observed_at": "2026-06-25T12:00:00Z"
  },
  {
    "inspection_id": "fixture",
    "component": "doris",
    "metric_or_fact": "kline_freshness_seconds",
    "value": 900,
    "source": "simulation_fixture",
    "target": "kline_1min",
    "observed_at": "2026-06-25T12:00:00Z"
  }
]
```

`tests/fixtures/diagnosis/insufficient_evidence.json`：

```json
[
  {
    "inspection_id": "fixture",
    "component": "kafka",
    "metric_or_fact": "topic_advancing",
    "value": true,
    "source": "simulation_fixture",
    "target": "binance.trade.raw",
    "observed_at": "2026-06-25T12:00:00Z"
  }
]
```

`tests/fixtures/diagnosis/component_down.json`：

```json
[
  {
    "inspection_id": "fixture",
    "component": "collector",
    "metric_or_fact": "service_state",
    "value": {"state": "NOT_RUNNING"},
    "source": "simulation_fixture",
    "target": "data1",
    "observed_at": "2026-06-25T12:00:00Z"
  }
]
```

`tests/fixtures/diagnosis/flink_backpressure.json`：

```json
[
  {
    "inspection_id": "fixture",
    "component": "flink",
    "metric_or_fact": "backpressure_level",
    "value": "high",
    "source": "simulation_fixture",
    "target": "streamlake-kline-aggregation",
    "observed_at": "2026-06-25T12:00:00Z"
  },
  {
    "inspection_id": "fixture",
    "component": "flink",
    "metric_or_fact": "checkpoint_consecutive_failures",
    "value": 3,
    "source": "simulation_fixture",
    "target": "streamlake-kline-aggregation",
    "observed_at": "2026-06-25T12:00:00Z"
  }
]
```

`tests/fixtures/diagnosis/configuration_mismatch.json`：

```json
[
  {
    "inspection_id": "fixture",
    "component": "flink",
    "metric_or_fact": "configuration_resolution",
    "value": {
      "key": "WHALE_THRESHOLD",
      "expected_source": "mysql",
      "effective_source": "default"
    },
    "source": "simulation_fixture",
    "target": "streamlake-whale-cep",
    "observed_at": "2026-06-25T12:00:00Z"
  }
]
```

- [ ] **Step 2：写 CLI 成功场景测试**

```python
def test_diagnose_kline_fixture_and_show_round_trip(tmp_path: Path) -> None:
    database_path = tmp_path / "datasentry.db"
    result = runner.invoke(
        app,
        [
            "inspection",
            "diagnose",
            "--question",
            "为什么K线不更新",
            "--observations-file",
            str(FIXTURES / "kline_job_missing.json"),
            "--knowledge-root",
            str(REPOSITORY_ROOT / "knowledge"),
            "--database-path",
            str(database_path),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["route"]["question_type"] == "data_stale"
    assert [item["topic_id"] for item in payload["knowledge"]] == ["03", "04"]
    assert payload["aggregate"]["findings"][0]["claim"] == "K线链路停在 Flink 计算层"
    assert payload["aggregate"]["findings"][0]["status"] == "inferred"
```

- [ ] **Step 3：写 CLI 安全失败测试**

```python
def test_diagnose_rejects_invalid_observation_json(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"token": "secret"}', encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "inspection",
            "diagnose",
            "--question",
            "为什么K线不更新",
            "--observations-file",
            str(invalid),
            "--knowledge-root",
            str(REPOSITORY_ROOT / "knowledge"),
            "--database-path",
            str(tmp_path / "datasentry.db"),
        ],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stderr)
    assert payload["code"] == "diagnosis.invalid_observations"
    assert "secret" not in result.stderr


def test_diagnose_rejects_missing_knowledge_root(tmp_path: Path) -> None:
    missing_root = tmp_path / "missing"
    result = runner.invoke(
        app,
        [
            "inspection",
            "diagnose",
            "--question",
            "为什么K线不更新",
            "--observations-file",
            str(FIXTURES / "kline_job_missing.json"),
            "--knowledge-root",
            str(missing_root),
            "--database-path",
            str(tmp_path / "datasentry.db"),
        ],
    )
    assert result.exit_code == 2
    assert json.loads(result.stderr)["code"] == "knowledge.index_missing"
```

- [ ] **Step 4：运行场景测试确认失败**

Run:

```bash
.venv/bin/pytest tests/scenarios/test_cli_knowledge_diagnosis.py -q
```

Expected: FAIL，提示不存在 `inspection diagnose` 命令。

- [ ] **Step 5：实现 CLI 命令与安全 JSON 解析**

新增选项：

```python
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
```

解析要求：

- 文件顶层必须是 JSON array。
- 每项通过 `Observation.model_validate()` 校验。
- 捕获 `OSError`、`JSONDecodeError` 和 Pydantic `ValidationError`，统一转换为：

```json
{
  "code": "diagnosis.invalid_observations",
  "message": "模拟 Observation 文件无效",
  "details": {}
}
```

- 错误不得回显原始文件内容。
- CLI 构造 `KnowledgeIndex`、`KnowledgeRouter`、血缘图、四条规则和 `DiagnosisService`。
- 输出键固定为 `route`、`knowledge`、`lineage_checkpoints`、`aggregate`。

- [ ] **Step 6：验证全部 CLI 场景**

Run:

```bash
.venv/bin/pytest tests/scenarios/test_cli_knowledge_diagnosis.py -q
.venv/bin/pytest tests/scenarios/test_cli_simulated_inspection.py -q
.venv/bin/ruff format --check src tests
.venv/bin/ruff check src tests
.venv/bin/mypy src
```

Expected: 全部退出码为 `0`，M0 `simulate/show` 行为无回归。

- [ ] **Step 7：提交诊断 CLI**

```bash
git add src/datasentry/cli/app.py tests/fixtures/diagnosis tests/scenarios
git diff --cached --check
git commit -m "feat: 增加知识驱动诊断 CLI"
```

### Task 9：更新文档、状态并完成 M1 全量验证

**Files:**

- Modify: `README.md`
- Modify: `docs/PROJECT_STATUS.md`

- [ ] **Step 1：更新 README 使用说明**

增加“M1 本地知识诊断”章节，包含：

```bash
datasentry inspection diagnose \
  --question "为什么K线不更新" \
  --observations-file tests/fixtures/diagnosis/kline_job_missing.json \
  --knowledge-root knowledge \
  --database-path /tmp/datasentry-m1.db
```

明确说明：

- fixture 是模拟现场 Observation。
- M1 未接入生产系统。
- Markdown 知识是稳定背景或历史引用，不代表当前运行事实。
- 真实只读查询属于 M2。

- [ ] **Step 2：运行全量质量门禁**

Run:

```bash
.venv/bin/ruff format --check .
.venv/bin/ruff check .
.venv/bin/mypy src
.venv/bin/pytest -q -W error
.venv/bin/pytest --cov=datasentry --cov-report=term-missing --cov-fail-under=90
.venv/bin/python -m build
```

Expected:

- 所有命令退出码为 `0`。
- 不出现 `ResourceWarning`。
- 覆盖率不低于 `90%`。
- `dist/` 生成 wheel 和 sdist。

- [ ] **Step 3：执行验收场景**

Run:

```bash
rm -f /tmp/datasentry-m1.db
.venv/bin/datasentry db upgrade --database-path /tmp/datasentry-m1.db
.venv/bin/datasentry inspection diagnose \
  --question "为什么K线不更新" \
  --observations-file tests/fixtures/diagnosis/kline_job_missing.json \
  --knowledge-root knowledge \
  --database-path /tmp/datasentry-m1.db
```

Expected:

- schema 版本仍为 `1`。
- 诊断命令退出码为 `0`。
- 结果满足第 1.3 节全部断言。

- [ ] **Step 4：同步项目状态**

`docs/PROJECT_STATUS.md` 更新为：

- 当前阶段：`M1：知识驱动诊断`。
- 已完成：知识索引、路由、血缘、确定性规则和模拟诊断 CLI。
- 下一步：评审 M1，随后创建 M2 真实只读工具详细计划。
- 已知风险新增：Inspection 聚合当前缺少跨多次 Repository 写入的 Unit of Work，持久化中途失败可能留下不完整记录；在引入异步 Worker 或真实工具前处理。
- 明确生产权限仍未接入。

- [ ] **Step 5：检查 diff 和秘密**

Run:

```bash
git status --short
git diff --check
git diff --stat
git diff -- src tests README.md docs/PROJECT_STATUS.md
```

Expected:

- 无意外文件、缓存、数据库、构建产物或秘密进入暂存范围。
- 所有用户文案、注释和 docstring 使用中文；代码标识符与 JSON 字段使用英文。

- [ ] **Step 6：提交 M1 文档和状态**

```bash
git add README.md docs/PROJECT_STATUS.md
git diff --cached --check
git commit -m "docs: 更新 M1 使用说明和项目状态"
```

## 6. 里程碑与提交检查点

建议保持以下九个可恢复提交：

1. `feat: 增加知识索引解析`
2. `feat: 增加确定性知识路由`
3. `feat: 建立 StreamLake 显式血缘`
4. `feat: 增加诊断规则基础契约`
5. `feat: 增加首批确定性诊断规则`
6. `feat: 编排知识驱动诊断`
7. `test: 校验知识库与血缘目录一致性`
8. `feat: 增加知识驱动诊断 CLI`
9. `docs: 更新 M1 使用说明和项目状态`

M1 属于较大功能，应在独立分支实施，例如：

```bash
git switch -c feat/m1-knowledge-diagnosis
```

完成全量验证后再按仓库规则推送并创建 Pull Request。推送前先拉取并检查远端变化；存在分叉或冲突时停止说明，不覆盖远端。

## 7. M1 完成检查表

- [ ] `knowledge/INDEX.md` 文档地图和快速路由均被真实解析。
- [ ] 每次问题只加载 1～3 份主题文档。
- [ ] 四类问题路由有参数化测试。
- [ ] Kline、Whale、Risk 主要血缘可遍历。
- [ ] 四条首批规则均为纯函数并覆盖命中与证据不足。
- [ ] “为什么K线不更新”场景定位到 Flink 计算层。
- [ ] 历史知识不会产生当前 `confirmed` Evidence。
- [ ] CLI 只读取本地模拟 Observation，不访问网络或生产组件。
- [ ] 诊断结果写入 SQLite 并可读回。
- [ ] M0 CLI 和存储测试无回归。
- [ ] Ruff、mypy、pytest、覆盖率和构建全部通过。
- [ ] `docs/PROJECT_STATUS.md` 与实际状态一致。
