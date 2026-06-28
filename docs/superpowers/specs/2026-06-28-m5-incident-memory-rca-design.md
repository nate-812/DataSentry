# M5 事件记忆与 RCA 设计

## 1. 文档状态

- 项目：StreamLake-Binance 智能运维 Agent
- 产品名：DataSentry
- 日期：2026-06-28
- 状态：已确认 M5 设计方向
- 适用范围：M5 Incident 生命周期、Alertmanager 自动建档、历史相似事件检索、RCA 复盘草稿、Markdown 导出和 SQLite 迁移评估

## 2. 目标与范围

M5 的目标是让 DataSentry 从“可诊断、可展示”进入“可记忆、可复盘”。当 Alertmanager Webhook 收到告警时，DataSentry 应复用现有只读诊断能力，自动创建或合并 Incident，记录完整时间线，关联巡检、Finding、证据、Operation 和聊天任务，并在后续同类故障发生时引用历史处理记录。

M5 首版选择完整闭环：Alertmanager 作为主要自动入口，IncidentService 作为事件记忆内核，SQLite 保存结构化时间线和 RCA 草稿，React 控制台提供事件工作台。历史事件只能作为经验参考；当前诊断仍必须重新查询现场状态，不得把旧结论包装成当前事实。

纳入 M5：

- Alertmanager Webhook 自动 upsert Incident。
- Incident 自动创建、合并、更新、验证和关闭。
- Incident 时间线、关联链接、fingerprint 和 RCA 草稿持久化。
- 按组件、故障类型、severity、root cause 关键词和时间范围检索历史相似事件。
- RCA Markdown 草稿生成和导出。
- React `Incidents` 页面升级为事件工作台。
- 评估 SQLite 向 PostgreSQL 迁移条件和路径。

不纳入 M5：

- 生产写操作、真实 Runbook 执行、自动重启、自动补数、自动改配置或 Savepoint 恢复。
- 任意 Shell、任意 SQL、自由日志路径或生产配置修改。
- 向量库、RAG、全文检索服务或 PostgreSQL 实际迁移。
- 多用户 RBAC、SSO、权限审批和 M6 真实执行器。
- 读取 MySQL 异常表 `RECOVER_YOUR_DATA_info` 内容。

## 3. 关键选择

| 主题 | 选择 | 原因 |
|---|---|---|
| 主入口 | Alertmanager Webhook 自动建档 | 与 M3 告警和 M4 API 已有能力自然连接 |
| 事件内核 | 新增 `datasentry.incidents` 模块 | 将生命周期、合并、检索和 RCA 从 API 层分离 |
| 自动合并 | 活跃 Incident + fingerprint + 时间窗口 | 避免同一持续故障反复创建事件 |
| RCA 生成 | 确定性模板优先，LLM 只做可读润色 | 保留可解释证据，模型不可用时仍能复盘 |
| 历史检索 | SQLite 结构化查询 | 可测试、可解释，不引入 RAG 复杂度 |
| 前端形态 | Incident 事件工作台 | 从列表升级为可处理、可复盘的运维视图 |
| 数据库迁移 | M5 只评估 PostgreSQL，不迁移 | 当前单机 SQLite 仍能支撑首版，避免阶段膨胀 |

## 4. 总体架构

```text
Alertmanager Webhook
→ AlertmanagerPayload 解析
→ NotificationService / LiveInspectionService
→ DiagnosisService 与确定性规则
→ IncidentService
→ SQLite Repository
→ Incident API / RCA API
→ React Incident 工作台
```

`IncidentService` 是 M5 的核心边界。它接收告警上下文、诊断结果、Operation 状态变化和人工触发请求，负责计算 fingerprint、查找活跃 Incident、写入时间线、关联证据、更新状态并生成 RCA 草稿。API 路由只负责协议转换和错误返回，不在路由中散落生命周期判断。

建议新增目录：

```text
src/datasentry/
└── incidents/
    ├── __init__.py
    ├── fingerprints.py
    ├── lifecycle.py
    ├── models.py
    ├── rca.py
    ├── search.py
    └── service.py
```

## 5. Incident 生命周期

M5 沿用总体架构中的状态机：

```text
open → investigating → awaiting_approval → mitigating → verifying → resolved
```

失败、拒绝或证据不足时可进入：

```text
blocked / escalated
```

首版自动流转规则保持保守：

- 新告警触发且没有匹配活跃 Incident：创建 `open` Incident，随后进入 `investigating`。
- 新告警触发且存在匹配活跃 Incident：更新 `updated_at`、severity 和时间线，不覆盖已确认 root cause。
- 诊断成功且存在 confirmed Finding：记录 Finding 链接，更新 root cause 草稿和建议。
- 诊断失败或全部证据为 unknown：进入或保持 `blocked`，要求人工继续处理。
- Alertmanager resolved 信号到达：记录 `alert_resolved`，进入 `verifying`。
- 只读验证通过：进入 `resolved`，写入 `resolved_at`。
- 只读验证失败：回到 `investigating` 或保持 `blocked`，记录失败原因。

M5 不自动进入 `awaiting_approval`、`mitigating` 或执行真实修复；这些状态仅用于关联已有 Operation 或为 M6 保留。

## 6. 数据模型与存储

新增 SQLite 迁移 `0004_incident_memory.sql`：

- `incident_links`：把 Incident 关联到 `inspection`、`finding`、`operation`、`alert`、`chat_run` 和 `rca_report`。
- `incident_timeline_events`：保存事件时间线，包含类型、摘要、source、payload JSON 和时间。
- `incident_fingerprints`：保存组件、故障类型、稳定标签 hash、severity 和首末观察时间。
- `incident_rca_reports`：保存 RCA 草稿版本、Markdown、结构化 JSON、生成方式和时间。

建议的时间线事件类型：

```text
alert_fired
alert_resolved
diagnosis_started
diagnosis_completed
diagnosis_failed
finding_added
operation_linked
status_changed
verification_completed
rca_generated
manual_note_added
```

Repository 增加：

- `save_incident_link`、`list_incident_links`。
- `save_timeline_event`、`list_timeline_events`。
- `save_incident_fingerprint`、`find_active_incident_by_fingerprint`。
- `search_similar_incidents`。
- `save_rca_report`、`get_latest_rca_report`、`list_rca_reports`。

所有 JSON payload 入库前必须脱敏。`payload_json` 只保存可展示摘要、稳定 ID、时间、状态和证据引用，不保存 secret、Authorization、Cookie、SSH key、数据库密码、完整连接串或自由命令文本。

## 7. Fingerprint 与历史检索

fingerprint 由以下字段构成：

- `component`：来自 Alertmanager labels、Finding evidence 或诊断问题映射。
- `failure_type`：来自 alertname、诊断路由主题或 Finding claim 分类。
- `stable_labels_hash`：只包含稳定标签，如 `alertname`、`component`、`service`、`job`、`instance`。
- `severity`：取告警和 Finding 中更高的级别。

自动合并只匹配未关闭 Incident，并限制在最近活跃时间窗口内。历史相似事件检索可以扩大时间范围，但返回结果必须标记为 historical context。检索排序按 fingerprint 完全匹配、组件匹配、故障类型匹配、root cause 关键词匹配、时间接近度和 severity 接近度综合排序。

首版不做向量检索、不调用外部搜索服务。这样能保证历史引用来源清楚，也便于用固定 fixture 写回归测试。

## 8. 后端 API 设计

### 8.1 Alertmanager Webhook

`POST /api/alertmanager/webhook` 在 M5 中升级为：

1. 解析 Alertmanager payload。
2. 映射诊断问题。
3. 执行只读诊断。
4. upsert Incident。
5. 写入时间线和证据链接。
6. 返回处理摘要。

响应示例：

```json
{
  "accepted": true,
  "incident_id": "incident_123",
  "action": "created",
  "status": "investigating",
  "deduplication_key": "alertname=KlineFreshnessStale|component=flink|startsAt=...",
  "diagnosis_question": "为什么 K线数据不更新"
}
```

`action` 固定为：

```text
created
updated
resolved_signal_recorded
diagnosis_failed
ignored
```

### 8.2 Incident API

- `GET /api/incidents`：按更新时间倒序列出 Incident，支持 `status`、`severity`、`component`、`limit`。
- `GET /api/incidents/{incident_id}`：返回 Incident、links、timeline、fingerprint 和最新 RCA。
- `GET /api/incidents/{incident_id}/timeline`：返回时间线。
- `GET /api/incidents/{incident_id}/similar`：返回历史相似事件。
- `POST /api/incidents/{incident_id}/rca`：生成或刷新 RCA 草稿。
- `GET /api/incidents/{incident_id}/export`：导出 Markdown 复盘稿。

### 8.3 Chat 与 Operation 关联

M5 不要求 Chat 自动创建 Incident，但支持将 chat run 关联到已有 Incident。Operation 仍沿用 M4 模拟审批边界；当 Operation 存在 `incident_id` 时，M5 只追加时间线和 RCA 材料，不触发真实执行。

## 9. RCA 设计

RCA 草稿使用确定性模板生成，结构固定：

1. 事件摘要：标题、状态、severity、影响窗口、当前处理状态。
2. 时间线：告警触发、诊断完成、Finding 产生、状态变化、验证和关闭。
3. 根因判断：分别列出 confirmed、inferred、unknown 和 historical。
4. 证据清单：source、target、observed_at、summary 和关联 Finding。
5. 处置与验证：关联 Operation、验证结果和仍需人工确认的事项。
6. 历史相似事件：只作为参考经验，明确不能替代本次现场查询。
7. 后续改进项：来自 Finding recommendation、unknowns 和人工 note。

LLM provider 可用于润色 RCA 的中文表达，但不能新增未在结构化上下文中出现的事实。LLM 不可用时，确定性模板直接产出 Markdown。

导出的 Markdown 必须包含边界声明：

```text
历史事件仅用于经验参考；当前状态必须以本次只读巡检证据为准。
```

## 10. React 事件工作台

`frontend/src/pages/IncidentsPage.tsx` 从简单列表升级为事件工作台：

- 左侧：Incident 列表，支持状态、severity 和组件筛选。
- 右侧：Incident 详情、fingerprint、当前状态和更新时间。
- 时间线：按时间展示告警、诊断、Finding、状态变化和 RCA 生成。
- 证据：展示关联 inspection、Finding 和 evidence 摘要。
- 历史：展示相似事件和处理记录。
- RCA：展示最新草稿，提供刷新和 Markdown 导出入口。

首版不做富文本编辑器，也不在前端保存 secret。导出入口从 API 获取 Markdown 文本，前端只负责展示或下载。

## 11. PostgreSQL 迁移评估

M5 不实际迁移数据库，但输出迁移评估结论。评估条件：

- 多用户并发写入或多个 DataSentry 实例同时处理告警。
- Incident 时间线和 RCA 数量增长到 SQLite 写锁成为瓶颈。
- 需要跨环境共享事件记忆。
- 需要更强的全文检索、分区、审计或备份恢复能力。

建议迁移路径：

1. 保持 Repository 协议稳定。
2. 为 PostgreSQL 新增 adapter。
3. 使用同一组 Repository 集成测试验证 SQLite 和 PostgreSQL 行为一致。
4. 提供一次性导出导入脚本。
5. 在生产切换前执行只读影子验证。

## 12. 错误处理与安全

- Alertmanager 自动入口只允许只读诊断和本地事件记忆写入。
- 当前状态必须来自现场只读工具；历史结论只能以 `historical` 身份引用。
- API 错误统一返回安全错误码和中文 message，不返回 traceback、SQL、secret 或连接串。
- 单个工具失败不阻断 Incident 建档；时间线记录诊断失败和 unknown。
- RCA、timeline payload、通知摘要和 API 返回都必须脱敏。
- 不读取 Shell history、SSH 私钥、系统钥匙串、真实 `.env` 或工作区外敏感文件。
- 不读取 MySQL 异常表 `RECOVER_YOUR_DATA_info` 内容。

## 13. 测试策略

后端测试：

- fingerprint：稳定标签排序、缺失标签、severity 合并和 hash 稳定性。
- lifecycle：created、updated、resolved signal、verification pass、verification fail、diagnosis failed。
- Repository：links、timeline、fingerprints、RCA reports 和相似事件检索。
- Alertmanager API：新告警创建 Incident、重复告警合并、resolved 信号进入 verifying。
- RCA：确定性 Markdown 包含时间线、证据、未知项、历史边界声明和脱敏结果。
- 安全回归：password、token、Authorization、Cookie、数据库连接串不进入 timeline、RCA、API 响应或 SQLite payload。

前端测试：

- TypeScript 类型检查。
- Incident 工作台列表和详情渲染。
- 时间线、相似事件和 RCA Markdown 展示。
- RCA 刷新和导出入口的 API 调用。

端到端验证：

- 使用本地 SQLite 和 Alertmanager fixture 调用 Webhook。
- 验证 Incident 创建、重复告警合并、时间线追加和 RCA 生成。
- 在 React 控制台查看事件详情、证据、历史相似事件和 RCA 草稿。
- 全量运行 Ruff、mypy、pytest、前端 typecheck 和 build。

## 14. 退出标准

M5 完成时必须满足：

1. Alertmanager Webhook 能自动创建或合并 Incident，并返回 `incident_id`。
2. 同一持续故障重复告警不会反复创建 Incident。
3. Incident 详情能展示完整时间线、证据链接、历史相似事件和最新 RCA。
4. RCA Markdown 能导出完整事故时间线、证据、根因判断、未知项和后续建议。
5. 同类故障再次发生时可以引用历史处理记录，但当前诊断仍重新查询现场状态。
6. M5 不执行任何生产写操作，不读取异常 MySQL 表内容，不引入 RAG 或任意 Shell。
7. 后端 Ruff、mypy、pytest 和前端 typecheck/build 通过。
8. README 和 `docs/PROJECT_STATUS.md` 记录 M5 使用方式、边界、验证结果和 PostgreSQL 迁移评估结论。
