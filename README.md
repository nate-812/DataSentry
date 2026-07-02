# DataSentry

DataSentry 是面向 StreamLake-Binance 的证据驱动智能运维 Agent。当前已完成
真实只读巡检、监控通知、FastAPI Agent、React Command Center、Incident/RCA、
审批式 Runbook、有限自治控制面、M8 监控部署闭环复验；M9 正在收口
DataSentry API 的 `data1` 本机 loopback 部署、Alertmanager 自动回调、secret
与公网暴露面边界。

> M2 只允许固定 HTTP GET、固定 SSH 命令、固定数据库 SELECT 和受限 Redis
> 查询。项目不提供任意 Shell、任意 SQL、任意 URL 或任何生产写操作。

## 本地开发

要求 Python 3.12 或 3.13：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

## M0 CLI

升级本地数据库：

```bash
datasentry db upgrade --database-path /tmp/datasentry.db
```

创建一次模拟巡检：

```bash
datasentry inspection simulate \
  --database-path /tmp/datasentry.db \
  --question "M0 模拟巡检"
```

读取巡检：

```bash
datasentry inspection show INSPECTION_ID \
  --database-path /tmp/datasentry.db
```

模拟输出包含 `production_access: false`，用于明确表示没有查询生产系统。

## M1 本地知识诊断

使用固定模拟 Observation 诊断“K线不更新”：

```bash
datasentry inspection diagnose \
  --question "为什么K线不更新" \
  --observations-file tests/fixtures/diagnosis/kline_job_missing.json \
  --knowledge-root knowledge \
  --database-path /tmp/datasentry-m1.db
```

输出包含：

- 问题类型与实际加载的 1～3 份主题知识。
- Collector → Kafka → Flink → Doris/API 的有序检查链路。
- 模拟 Observation、确定性 Finding、证据、未知项和建议。
- 可通过 `datasentry inspection show INSPECTION_ID` 读回的 SQLite 巡检记录。

fixture 只模拟现场 Observation。Markdown 知识用于稳定背景和历史引用，不代表当前运行事实；真实 Flink、Kafka、Doris、Redis、MySQL、主机和日志查询属于 M2。

## M2 真实只读巡检

复制目标配置示例，但不要提交真实目标文件：

```bash
cp config/targets.example.toml config/targets.toml
```

`config/targets.toml` 已被 Git 忽略。文件只保存目标别名、地址、端口、用户名、
known_hosts 和秘密环境变量名称；密码、Token 和私钥内容不得写入该文件。

真实凭据通过当前进程环境注入，例如：

```bash
export DATASENTRY_DORIS_PASSWORD='在本机安全设置'
export DATASENTRY_MYSQL_PASSWORD='在本机安全设置'
export DATASENTRY_REDIS_PASSWORD='在本机安全设置'
```

执行真实只读 Kline 巡检：

```bash
datasentry inspection run \
  --question "为什么K线不更新" \
  --targets-file config/targets.toml \
  --knowledge-root knowledge \
  --database-path var/datasentry-m2.db
```

输出包含工具调用审计、现场 Observation、Finding 和 unknown。单个工具超时或解析
失败不会终止其余查询。首次连接云端前必须确认：

- SSH 账号无 `sudo` 和写权限，并预置可信 known_hosts。
- Doris/MySQL 账号仅允许 `SELECT`、`SHOW`、`DESCRIBE`。
- Redis ACL 仅允许计划内只读命令，禁止 `KEYS`。
- Flink、Spring API 和 AI Engine 只通过内网访问。
- 日志仅配置固定组件和固定路径，最多 200 行或 30 分钟。

## M3 监控与通知本地验证

M3 提供 Prometheus、Alertmanager、Grafana 配置模板，以及 Alertmanager
载荷到 DataSentry 诊断消息的本地模拟命令。以下命令只读取本地 fixture 和
占位监控资产，不会发送真实网络通知，也不会部署 Prometheus、Grafana 或
Alertmanager。

输出企业微信 Markdown 载荷：

```bash
datasentry notification simulate \
  --payload-file tests/fixtures/alertmanager/kline_freshness_firing.json \
  --format wecom \
  --database-path var/datasentry.db
```

输出通用 Webhook JSON：

```bash
datasentry notification simulate \
  --payload-file tests/fixtures/alertmanager/kline_freshness_firing.json \
  --format generic \
  --database-path var/datasentry.db
```

监控模板位于：

- `monitoring/prometheus/`：Prometheus scrape 示例和 StreamLake 告警规则。
- `monitoring/alertmanager/`：Alertmanager 路由、抑制和企业微信占位 receiver。
- `monitoring/grafana/`：Prometheus datasource、dashboard provisioning 和六个 dashboard JSON。

真实企业微信机器人 key、Webhook URL、认证 token 和生产目标配置必须由部署环境
注入，不得提交到 Git。

## M4 对话 Agent 与 Web 控制台

升级本地数据库后启动 FastAPI：

```bash
datasentry db upgrade --database-path var/datasentry-m4.db
DATASENTRY_DATABASE_PATH=var/datasentry-m4.db \
DATASENTRY_TARGETS_FILE=config/targets.example.toml \
DATASENTRY_LLM_PROVIDER=mock \
  uvicorn datasentry.api:create_app --factory --host 127.0.0.1 --port 8000
```

启动 React 控制台：

```bash
cd frontend
npm install
npm run dev
```

控制台默认访问 `http://127.0.0.1:8000`，可通过
`VITE_DATASENTRY_API_BASE` 指向其他 DataSentry API。M4 首版页面包含概览、
对话诊断、Incident、证据、模拟审批和 Grafana 入口。Web 控制台不直连生产组件，
只访问 DataSentry API。

LLM 首版按 API key 优先设计，不默认依赖本地大模型：

```bash
export DATASENTRY_LLM_PROVIDER=openai_compatible
export DATASENTRY_LLM_BASE_URL='https://llm.example.test/v1'
export DATASENTRY_LLM_MODEL='ops-model'
export DATASENTRY_LLM_API_KEY='只在本机环境中设置'
```

未配置或调用失败时，诊断仍使用确定性中文模板回答。API key 不会返回到
`/api/health`、前端响应、日志或异常详情。

本地模拟审批只允许 `simulate_` 前缀 Operation，批准或拒绝只更新 SQLite 状态，
不执行生产 Runbook。

## M5 事件记忆与 RCA

M5 开发和主要验证不需要打开云实例。使用本地 SQLite、Alertmanager fixture、
模拟诊断和前端构建即可验证自动建档、Incident 合并、时间线、历史相似事件、
RCA 草稿和 Markdown 导出。云实例只用于末尾可选的只读 smoke，不作为本地开发前置条件。

升级本地数据库并启动 API：

```bash
datasentry db upgrade --database-path var/datasentry-m5.db
DATASENTRY_DATABASE_PATH=var/datasentry-m5.db \
DATASENTRY_TARGETS_FILE=config/targets.example.toml \
DATASENTRY_LLM_PROVIDER=mock \
  uvicorn datasentry.api:create_app --factory --host 127.0.0.1 --port 8000
```

用本地 Alertmanager fixture 创建或合并 Incident：

```bash
curl -sS -X POST http://127.0.0.1:8000/api/alertmanager/webhook \
  -H 'Content-Type: application/json' \
  --data @tests/fixtures/alertmanager/kline_freshness_firing.json
```

Incident API 包含：

- `GET /api/incidents/{incident_id}`：读取 Incident 详情、关联证据、时间线、相似事件和最新 RCA。
- `GET /api/incidents/{incident_id}/timeline`：读取时间线。
- `GET /api/incidents/{incident_id}/similar`：读取历史相似 Incident。
- `POST /api/incidents/{incident_id}/rca`：生成并保存确定性 RCA 草稿。
- `GET /api/incidents/{incident_id}/export`：导出 Markdown 复盘草稿。

React 控制台的 Incident 页面已升级为事件工作台，可查看状态、严重级别、
时间线、关联巡检、相似事件、RCA 预览和 Markdown 导出。M5 仍保持只读诊断边界：
RCA 和历史记忆只作为经验参考，当前事实必须来自本次受限只读巡检证据；不实现 RAG、
任意 Shell、自动重启、自动补数、自动改配置、自动 Savepoint 恢复，也不读取
MySQL 异常表内容。

## M6 审批式自动运维

M6 第一版使用 Mock/本地受控执行器，不需要云端实例在线，也不会执行生产写操作。
它覆盖 Runbook 目录、Operation 创建、审批、拒绝、取消、执行、审计事件、
幂等复用、操作锁和操作后验证。本阶段仍禁止任意 Shell、自动重启、自动补数、
自动改配置、自动 Savepoint 恢复和删除数据。

升级本地数据库并启动 API：

```bash
datasentry db upgrade --database-path var/datasentry-m6.db
DATASENTRY_DATABASE_PATH=var/datasentry-m6.db \
DATASENTRY_TARGETS_FILE=config/targets.example.toml \
DATASENTRY_LLM_PROVIDER=mock \
  uvicorn datasentry.api:create_app --factory --host 127.0.0.1 --port 8000
```

Runbook API 包含：

- `GET /api/runbooks`：读取内置 Runbook 目录。
- `POST /api/operations`：提交 Runbook Operation，必填 `target` 和 `reason`。
- `POST /api/operations/{operation_id}/approve`：审批 Operation。
- `POST /api/operations/{operation_id}/reject`：拒绝 Operation。
- `POST /api/operations/{operation_id}/cancel`：取消待审批 Operation。
- `POST /api/operations/{operation_id}/execute`：执行已审批的 mock Runbook 并做操作后验证。
- `GET /api/operations/{operation_id}/events`：读取审计事件。

React 控制台的审批页已升级为 Runbook 操作台，可创建 mock Runbook Operation，
推进审批和执行，并查看参数、结果和审计事件。旧的
`POST /api/operations/simulations` 入口保留兼容，但批准后需要通过执行接口进入
`succeeded`。

## M7 有限自治

M7 第一版增加本地有限自治控制层，默认策略为 disabled + shadow，不会自动执行
真实生产操作。本阶段只允许 mock Runbook 参与自治评估，所有真实 SSH、Shell、
SQL 写入、Savepoint、补数、配置修改和删除数据仍被禁止。

新增 API 包含：

- `GET /api/autonomy/policies`：读取自治策略。
- `PATCH /api/autonomy/policies/{runbook_name}`：开启或关闭策略与 shadow 模式。
- `POST /api/autonomy/evaluate`：只评估候选，不创建 Operation。
- `POST /api/autonomy/execute`：按策略记录 shadow、阻止、升级或执行本地 mock Operation。
- `GET /api/autonomy/runs`：读取最近自治决策记录。
- `GET /api/autonomy/stats`：按 Runbook 汇总自治样本、成功率、升级和准入状态。
- `POST /api/autonomy/circuit-breakers/{runbook_name}/half-open`：将本地 mock 熔断状态切到 half-open。
- `POST /api/autonomy/circuit-breakers/{runbook_name}/reset`：将本地 mock 熔断状态重置为 closed。

本地演练流程：

1. 启动 DataSentry API。
2. 在审批页面查看“有限自治”区域。
3. 打开 `mock.restart_preview` 的 shadow 策略并执行演练。
4. 确认页面只记录 shadow 决策，不创建 Operation。
5. 关闭 shadow 后再次演练，确认仅本地 mock Operation 会自动创建、批准、执行和验证。
6. 在自治统计中查看成功率、样本数和准入状态；必要时只对本地 mock 策略执行 half-open 或 reset。

M7 开发不要求打开云实例。云端或测试环境只用于后续只读 smoke、人工审批低风险演练、
成功率样本收集和生产自治评估。

## M7.2 运维可用化

M7.2 增加 live smoke 预检入口，用于在真实只读巡检前检查目标配置和本地 secret
注入状态：

```bash
datasentry ops preflight \
  --targets-file config/targets.toml
```

输出只包含目标别名、环境变量名、`configured`/`missing` 状态和云端常见变量名提示，
不会打印 secret 值。Doris、MySQL、Redis 的云端作业变量与 DataSentry 本地巡检变量
可能需要映射：

| 云端变量 | DataSentry 变量 |
|---|---|
| `DORIS_PASSWORD` | `DATASENTRY_DORIS_PASSWORD` |
| `MYSQL_PASSWORD` | `DATASENTRY_MYSQL_PASSWORD` |
| `REDIS_PASSWORD` | `DATASENTRY_REDIS_PASSWORD` |

完整 live smoke 操作方式见
[`docs/operations/live-smoke.md`](docs/operations/live-smoke.md)。

## M8 监控部署闭环

M8 增加监控栈部署验收和 DataSentry 告警诊断闭环 smoke。监控栈仍由人工或现有运维
流程部署，DataSentry 只做只读验收和本地 Incident/RCA 闭环验证。

复制无 secret 配置示例：

```bash
cp config/monitoring.example.toml config/monitoring.toml
```

检查 Prometheus/Grafana/Alertmanager 真实部署状态：

```bash
datasentry monitoring deployment-check \
  --config-file config/monitoring.toml
```

验证 Alertmanager payload 能驱动 DataSentry Incident、timeline、RCA 和 Markdown export：

```bash
datasentry monitoring alert-smoke \
  --config-file config/monitoring.toml \
  --payload-file tests/fixtures/alertmanager/kline_freshness_firing.json
```

完整操作方式见
[`docs/operations/monitoring-deployment.md`](docs/operations/monitoring-deployment.md)。

## M9 生产化与安全收口

M9 将 DataSentry API 作为 `data1` 本机 loopback 服务运行，Alertmanager 通过
`http://127.0.0.1:18000/api/alertmanager/webhook` 回调，不把 DataSentry API
暴露到公网。开发、提交和版本管理仍以本地仓库与 GitHub 为准；云端只运行明确的
Git 版本。

仓库提供以下无 secret 示例和运维入口：

- `deploy/systemd/datasentry-api.service.example`
- `config/datasentry.env.example`
- [`docs/operations/m9-production-deployment.md`](docs/operations/m9-production-deployment.md)
- [`docs/operations/production-exposure-checklist.md`](docs/operations/production-exposure-checklist.md)

M9 不开放任意 Shell、任意 SQL、生产写操作、自动重启、自动补数、自动改配置或自动
Savepoint 恢复。DataSentry API、Prometheus、Grafana、Alertmanager、Flink Web、
Doris FE、MySQL、Redis、Spring API 和 AI Engine 均不应公网暴露；需要通过本机
loopback、内网或受控 SSH tunnel 访问。

## 配置

| 环境变量 | 默认值 | 用途 |
|---|---|---|
| `DATASENTRY_DATABASE_PATH` | `var/datasentry.db` | SQLite 数据库路径 |
| `DATASENTRY_TARGETS_FILE` | `config/targets.toml` | M2 目标配置路径 |
| `DATASENTRY_LOG_LEVEL` | `INFO` | 日志级别 |
| `DATASENTRY_LOG_FORMAT` | `json` | `json` 或 `console` |
| `DATASENTRY_ENVIRONMENT` | `development` | `development`、`test` 或 `production` |
| `DATASENTRY_API_HOST` | `127.0.0.1` | FastAPI 本地监听地址 |
| `DATASENTRY_API_PORT` | `8000` | FastAPI 本地监听端口 |
| `DATASENTRY_API_CORS_ORIGINS` | `["http://localhost:5173","http://127.0.0.1:5173"]` | 允许访问 API 的前端来源 |
| `DATASENTRY_GRAFANA_URL` | 空 | 控制台展示的 Grafana 链接 |
| `DATASENTRY_LLM_PROVIDER` | `disabled` | `disabled`、`mock` 或 `openai_compatible` |
| `DATASENTRY_LLM_BASE_URL` | 空 | OpenAI-compatible API base URL |
| `DATASENTRY_LLM_MODEL` | 空 | OpenAI-compatible 模型名称 |
| `DATASENTRY_LLM_API_KEY` | 空 | OpenAI-compatible API key，仅从环境读取 |
| `DATASENTRY_LLM_TIMEOUT_SECONDS` | `20` | 单次 LLM 请求超时秒数 |

真实秘密不得写入 `.env`、日志、SQLite、命令输出或 Git。

## 验证

```bash
ruff format --check .
ruff check .
mypy src
pytest tests -q -W error::ResourceWarning \
  --cov=datasentry \
  --cov-report=term-missing \
  --cov-fail-under=90
cd frontend && npm run typecheck
cd frontend && npm run build
```

## 知识库接入

Agent 新会话按顺序读取：

1. [`knowledge/INDEX.md`](knowledge/INDEX.md)
2. [`knowledge/09-agent-integration.md`](knowledge/09-agent-integration.md)
3. 根据索引只加载当前问题相关的 1～3 份主题文档

实时状态必须通过受限只读工具现场查询；历史快照不能包装成当前事实。

## 设计文档

- [`项目当前状态`](docs/PROJECT_STATUS.md)
- [`DataSentry 总体架构与开发路线设计`](docs/superpowers/specs/2026-06-25-datasentry-overall-architecture-design.md)
- [`M0 工程基础实施计划`](docs/superpowers/plans/2026-06-25-m0-engineering-foundation.md)
- [`M1 知识驱动诊断实施计划`](docs/superpowers/plans/2026-06-25-m1-knowledge-driven-diagnosis.md)
- [`M2 真实只读工具实施计划`](docs/superpowers/plans/2026-06-25-m2-real-readonly-tools.md)
- [`M3 监控看板与通知设计`](docs/superpowers/specs/2026-06-26-m3-observability-notifications-design.md)
- [`M3 监控看板与通知实施计划`](docs/superpowers/plans/2026-06-26-m3-observability-notifications.md)
- [`M4 对话式 Agent 与 Web 控制台设计`](docs/superpowers/specs/2026-06-27-m4-dialog-web-console-design.md)
- [`M4 对话式 Agent 与 Web 控制台实施计划`](docs/superpowers/plans/2026-06-27-m4-dialog-web-console.md)
- [`M5 事件记忆与 RCA 设计`](docs/superpowers/specs/2026-06-28-m5-incident-memory-rca-design.md)
- [`M5 事件记忆与 RCA 实施计划`](docs/superpowers/plans/2026-06-28-m5-incident-memory-rca.md)
- [`M7.2 运维可用化设计`](docs/superpowers/specs/2026-07-01-m7.2-ops-usability-design.md)
- [`M7.2 运维可用化实施计划`](docs/superpowers/plans/2026-07-01-m7.2-ops-usability.md)
- [`M8 监控部署闭环设计`](docs/superpowers/specs/2026-07-01-m8-monitoring-deployment-loop-design.md)
- [`M8 监控部署闭环实施计划`](docs/superpowers/plans/2026-07-01-m8-monitoring-deployment-loop.md)
- [`M9 生产化与安全收口设计`](docs/superpowers/specs/2026-07-02-m9-production-hardening-design.md)
- [`M9 生产化与安全收口实施计划`](docs/superpowers/plans/2026-07-02-m9-production-hardening.md)
- [`M9 生产化部署运维手册`](docs/operations/m9-production-deployment.md)
- [`生产暴露面收口 checklist`](docs/operations/production-exposure-checklist.md)
