# M4 对话式 Agent 与 Web 控制台设计

## 1. 文档状态

- 项目：StreamLake-Binance 智能运维 Agent
- 产品名：DataSentry
- 日期：2026-06-27
- 状态：已确认进入 M4 设计
- 适用范围：M4 对话式 Agent、FastAPI 服务、可插拔 LLM、React Web 控制台、事件和本地模拟审批首版

## 2. 目标与范围

M4 的目标是把 M0～M3 已完成的证据化诊断、真实只读工具、通知和自监控能力封装成可交互的 Web 控制台。用户应能在网页询问系统状态，DataSentry 使用白名单只读工具执行诊断，并展示结论、证据、工具来源、时间和未知项。

M4 首版选择完整 Web 控制台路径，而不是只做后端或只做聊天演示。首屏采用 Command Center 布局：左侧呈现系统概览、活跃告警、最近巡检和组件健康，右侧提供 Agent 对话、诊断进度和证据化回答。事件、证据、模拟审批和 Grafana 链接作为一级入口。

纳入 M4：

- FastAPI 服务、API 路由和 SSE 诊断进度推送。
- ChatService 对接现有 `LiveInspectionService` 和 `DiagnosisService`。
- OpenAI-compatible LLM provider、Mock provider 和模型不可用降级。
- React + TypeScript + Vite 控制台。
- 概览、聊天、事件、证据、模拟审批和 Grafana 跳转。
- Repository 增加列表查询和聊天会话/消息持久化。
- Alertmanager Webhook 进入 API 的统一入口。

不纳入 M4：

- 生产写操作、真实 Runbook 执行、自动重启、自动补数、自动改配置或 Savepoint 恢复。
- 完整 M5 事件记忆、RCA 复盘和历史相似事故检索。
- M6 审批式自动运维的真实执行器。
- 多用户权限、SSO、RBAC 和多实例任务调度。
- Loki/Alloy 集中日志接入。

## 3. 关键选择

| 主题 | 选择 | 原因 |
|---|---|---|
| Web 信息架构 | Command Center：概览 + 聊天并重 | 更贴近真实运维入口，既能值守也能提问 |
| LLM 首版 | OpenAI-compatible API key 优先，保留 Mock 和 disabled 降级 | 用户大概率使用 API key，不依赖本地大模型 |
| LLM 职责 | 只做可读总结和表达组织 | 规则、工具选择、权限和事实判定仍由确定性代码负责 |
| 进度推送 | SSE | 比 WebSocket 简单，适合单向诊断进度流 |
| 审批页 | 本地模拟审批状态流 | 让页面和状态体验完整，同时不触碰生产写操作 |
| 前端技术 | React + TypeScript + Vite + 普通 CSS | 足够轻量，便于本地开发和测试 |
| Grafana 集成 | 首版跳转或受控 iframe 配置 | 避免在 M4 绑定复杂认证和跨域问题 |

## 4. 总体架构

```text
React Command Center
→ FastAPI API
→ ChatService
→ LiveInspectionService
→ 白名单只读工具网关
→ DiagnosisService 与确定性规则
→ LLM Summarizer
→ SQLite Repository
→ SSE 事件流与 HTTP JSON 响应
```

Web 控制台不直接连接 Flink、Kafka、Doris、Redis、MySQL、主机、Prometheus 或 Grafana API。所有数据均来自 DataSentry API。LLM 也不直接调用工具，只接收已经脱敏、结构化的诊断上下文。

建议新增目录：

```text
src/datasentry/
├── api/
│   ├── app.py
│   ├── dependencies.py
│   ├── schemas.py
│   ├── routes/
│   │   ├── chat.py
│   │   ├── overview.py
│   │   ├── incidents.py
│   │   ├── operations.py
│   │   └── alertmanager.py
│   └── sse.py
├── chat/
│   ├── models.py
│   └── service.py
├── llm/
│   ├── models.py
│   ├── providers.py
│   └── summarizer.py
└── operations/
    └── simulation.py
frontend/
├── package.json
├── vite.config.ts
├── index.html
└── src/
    ├── api/
    ├── components/
    ├── pages/
    ├── styles/
    └── main.tsx
```

## 5. 后端 API 设计

### 5.1 基础 API

- `GET /api/health`：返回 API、数据库和 LLM 配置状态，不返回 API key。
- `GET /api/overview`：返回健康概览、最近巡检、活跃 Incident、待处理模拟审批、Grafana 链接和 DataSentry 自监控摘要。
- `GET /api/evidence/inspections/{inspection_id}`：返回巡检、Observation、Finding 和工具调用审计。

### 5.2 聊天与诊断 API

- `POST /api/chat/sessions`：创建聊天会话。
- `GET /api/chat/sessions`：列出最近会话。
- `GET /api/chat/sessions/{session_id}`：返回会话及消息。
- `POST /api/chat/sessions/{session_id}/runs`：提交用户问题并创建诊断任务。
- `GET /api/chat/runs/{run_id}/events`：通过 SSE 推送诊断进度。
- `GET /api/chat/runs/{run_id}`：返回任务状态和最终回答。

SSE 事件类型固定为：

```text
accepted
knowledge_loaded
tools_planned
tool_started
tool_finished
rules_completed
llm_started
llm_completed
completed
failed
```

事件内容必须脱敏，不包含 secret、Authorization、Cookie、数据库密码、SSH key、完整环境变量或自由命令文本。

### 5.3 Incident API

- `GET /api/incidents`：按更新时间倒序列出 Incident，支持 `status` 和 `limit`。
- `GET /api/incidents/{incident_id}`：返回 Incident 详情。

M4 只读取和展示已有 Incident 模型，不实现完整 RCA 生命周期。若聊天诊断需要创建 Incident，只能根据 Finding 生成最小 Incident 草稿，并保留证据引用。

### 5.4 模拟审批 API

- `GET /api/operations`：列出 Operation。
- `GET /api/operations/{operation_id}`：返回 Operation 详情。
- `POST /api/operations/simulations`：创建本地模拟审批申请。
- `POST /api/operations/{operation_id}/approve`：将模拟申请批准并标记模拟执行成功。
- `POST /api/operations/{operation_id}/reject`：拒绝模拟申请。

M4 仅允许名称以 `simulate_` 开头的本地 Operation 进入批准或拒绝接口。任何 `risk=forbidden` 或非模拟名称都必须拒绝。批准模拟只更新 SQLite 状态，不执行外部命令。

### 5.5 Alertmanager Webhook API

- `POST /api/alertmanager/webhook`：复用 M3 的 Alertmanager payload 解析、通知诊断映射和诊断消息格式。

首版可以同步返回本次处理摘要。后续如果真实 Alertmanager 需要快速确认接收，可切换为异步任务。

## 6. ChatService 与诊断回答

`ChatService` 负责把用户问题转成可追踪任务：

1. 保存用户消息。
2. 通过现有 `LiveInspectionService.run(question)` 执行真实只读巡检。
3. 汇总 `DiagnosisResult`、Observation、Finding 和 ToolInvocation。
4. 交给 `AnswerSummarizer` 生成中文回答。
5. 保存 Assistant 消息和关联的 `inspection_id`。
6. 发布 SSE 进度。

标准回答结构沿用总体架构：

1. 当前结论。
2. 已确认事实。
3. 推断。
4. 未知项。
5. 建议下一步。
6. 操作审批请求或说明。

LLM 不可用时，`AnswerSummarizer` 使用确定性模板生成回答。此时页面必须明确显示 `llm_status=unavailable` 或 `llm_status=disabled`，但诊断结果仍可用。

## 7. LLM 设计

新增统一接口：

```text
LLMProvider.generate(messages, options) -> LLMResult
AnswerSummarizer.summarize(context) -> AnswerSummary
```

Provider 类型：

- `disabled`：不调用模型，始终走确定性模板。
- `mock`：测试和演示用，返回稳定文本。
- `openai_compatible`：调用 Chat Completions 兼容 API。

建议配置：

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `DATASENTRY_LLM_PROVIDER` | `disabled` | `disabled`、`mock`、`openai_compatible` |
| `DATASENTRY_LLM_BASE_URL` | 空 | OpenAI-compatible API base URL |
| `DATASENTRY_LLM_MODEL` | 空 | 模型名称 |
| `DATASENTRY_LLM_API_KEY` | 空 | API key，只从环境变量读取 |
| `DATASENTRY_LLM_TIMEOUT_SECONDS` | `20` | 单次模型调用超时 |

安全约束：

- API key 不写入日志、SQLite、前端响应或错误详情。
- 发送给 LLM 的上下文只包含脱敏后的 Observation、Finding、ToolInvocation 摘要。
- Prompt 明确要求不得编造证据、不得把 unknown 写成 confirmed、不得生成 Shell/SQL/Redis 写命令。
- LLM 失败映射为结构化 `llm.unavailable` 或 `llm.upstream_error`，不影响规则诊断返回。

## 8. 存储扩展

新增 SQLite 迁移 `0003_chat_console.sql`：

- `chat_sessions`：会话 ID、标题、创建时间、更新时间。
- `chat_messages`：消息 ID、会话 ID、角色、内容、inspection_id、llm_status、created_at。
- `chat_runs`：任务 ID、会话 ID、用户消息 ID、状态、inspection_id、error_code、error_message、created_at、finished_at。
- `chat_run_events`：事件 ID、run_id、event_type、payload_json、created_at。

Repository 增加：

- `list_inspections(limit)`。
- `list_incidents(status, limit)`。
- `list_operations(status, limit)`。
- `save_chat_session`、`list_chat_sessions`、`get_chat_session`。
- `save_chat_message`、`list_chat_messages`。
- `save_chat_run`、`update_chat_run`、`list_chat_run_events`。

列表查询默认限制条数，避免 Web 首屏读取无边界历史数据。

## 9. React 控制台设计

首屏采用 Command Center：

- 顶部：环境、API 状态、LLM 状态、数据库路径提示、Grafana 链接。
- 左侧主区域：健康概览、组件状态矩阵、活跃告警、最近巡检、最新 Incident。
- 右侧固定区域：Agent 对话框、诊断进度、证据化回答。
- 一级页面：`Overview`、`Chat`、`Incidents`、`Evidence`、`Approvals`、`Grafana`。

页面职责：

- `Overview`：概览和最近状态。
- `Chat`：完整对话历史、SSE 进度、回答和证据引用。
- `Incidents`：Incident 列表和详情。
- `Evidence`：按 inspection 查看 Observation、Finding 和工具调用审计。
- `Approvals`：模拟审批列表、详情、批准和拒绝。
- `Grafana`：展示配置的外部链接；仅在明确配置时尝试 iframe。

前端不在本地存储 secret，不提供填写生产凭据的表单。生产目标配置仍使用后端环境和 ignored `config/targets.toml`。

## 10. 错误处理与安全

- API 错误统一返回 `{code, message, details}`，不泄露 SQL、secret、栈信息或底层连接字符串。
- 诊断单个工具失败不终止整次诊断，沿用 M2 局部失败隔离。
- SSE 失败事件必须包含安全错误码和中文 message。
- CORS 默认只允许本地开发来源；生产部署必须显式配置允许来源。
- API 默认不提供任何生产写接口。
- 模拟审批 API 对非模拟操作返回拒绝，不降级执行。
- 所有新增日志字段使用英文 key，message 使用中文。

## 11. 测试策略

后端测试：

- LLM provider：disabled、mock、OpenAI-compatible 成功、超时、认证失败和脱敏。
- ChatService：LLM 可用、LLM 不可用、工具局部失败、SSE 事件顺序。
- Repository：聊天会话、消息、run、event、列表查询。
- API：health、overview、chat、incidents、evidence、operations、Alertmanager webhook。
- 安全回归：API key、password、Authorization、Cookie 不进入响应、日志对象或 SQLite 消息。

前端测试：

- TypeScript 类型检查。
- Command Center 首屏渲染。
- Chat 提交问题、接收 SSE 进度、展示证据。
- Approvals 模拟批准和拒绝状态。

端到端验证：

- 使用本地 SQLite 和模拟目标配置启动 FastAPI。
- 启动 Vite 控制台。
- 在网页询问“K线为什么不更新”。
- 页面展示诊断进度、Finding、证据时间、工具来源和 LLM 降级状态。
- 创建模拟审批、批准和拒绝均只更新本地 SQLite。

## 12. 退出标准

M4 完成时必须满足：

1. 用户能在网页询问系统状态。
2. Agent 通过现有真实只读工具链回答，并展示证据时间和来源。
3. LLM 配置为 OpenAI-compatible 时可生成摘要；LLM 不可用或 disabled 时仍能完成规则诊断。
4. Web 可查看最近巡检、Incident、证据和工具调用。
5. Web 可创建并处理本地模拟审批，不执行生产写操作。
6. Alertmanager Webhook 可通过 FastAPI 入口接收并复用 M3 诊断消息链路。
7. 后端 Ruff、mypy、pytest 和前端类型检查通过。
8. README 和 `docs/PROJECT_STATUS.md` 记录 M4 使用方式、边界和未验证项。

