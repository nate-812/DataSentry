# M7 有限自治设计

## 1. 背景

DataSentry 已完成真实只读巡检、监控通知、对话控制台、Incident 记忆与 RCA，以及 M6 审批式 Runbook 本地闭环。M6 已经把 Runbook 请求、审批、执行、审计、幂等、并发锁和操作后验证串起来，但执行器仍限定为本地 mock，不触碰生产写操作。

M7 的目标不是第一次上线真实自动修复，而是在 M6 闭环前方增加“有限自治控制层”。该控制层先以本地 mock 和 shadow 模式运行，验证自动准入、维护窗口、速率限制、熔断、升级通知和成功率统计。只有长期验证过、低风险、可回滚且有明确操作后验证的 Runbook，后续才可能进入真实自动执行评估。

## 2. 目标

- 定义有限自治策略：自动执行范围、维护窗口、速率限制、熔断、升级和 shadow 模式。
- 增加自治候选评估结果，明确每一次自动执行、阻止执行或升级人工审批的原因。
- 复用 M6 `RunbookOperationService`，让自动路径仍经过现有 Operation、审计事件、幂等、锁和操作后验证。
- 记录自治执行统计，包括候选数、自动执行数、被策略阻止数、升级审批数、成功率和熔断状态。
- 提供 FastAPI 查询与控制接口，支持查看自治策略、统计、候选评估和手动打开或关闭自治策略。
- 扩展 React 审批操作台，使用户能看到自治模式、最近决策、熔断状态和 shadow 结果。
- 本地开发与主要验证不依赖云端实例，不执行真实 SSH、Shell、SQL 写入、Savepoint、补数或生产配置修改。

## 3. 非目标

- 不接入真实生产写执行器。
- 不自动执行 L2、L3 或 `forbidden` 风险操作。
- 不自动重启、停止服务、改配置、补数、删除数据、修改网络或执行 Savepoint 恢复。
- 不读取 `/root/bin` 脚本内容，也不把未审计脚本加入自动白名单。
- 不引入完整 RBAC、SSO、多租户或独立任务队列。
- 不要求云端实例在线；真实 Alertmanager smoke、测试环境演练和维护窗口人工审批执行是 M7 后续验收前置资料，不阻塞本地控制层开发。

## 4. 核心选择

推荐并采用“本地自治控制层优先”的路线：

1. 第一阶段只允许 `mock` 执行模式，且默认 `shadow_mode=true`。
2. 自动准入只覆盖 L0/L1 且显式标记为自治允许的 Runbook。
3. 控制层创建 Operation 时仍调用 M6 服务，确保幂等、锁、审计和验证不分叉。
4. shadow 模式只记录“如果打开自治会怎么处理”，不推进到 approve/execute。
5. 非 shadow 自动执行也只在本地 mock 中完成 approve/execute，用于验证 M7 控制逻辑，不代表生产写权限已经开放。

没有选择“直接接真实云端执行器”的原因：当前没有长期成功样本、专用执行用户、维护窗口演练和 `/root/bin` 源码审计结果。直接上线真实自动操作会越过既定安全路线。

## 5. 安全边界

M7 第一版默认拒绝以下情况：

- Runbook `execution_mode` 不是 `mock`。
- Runbook 风险不是 L0 或 L1。
- Runbook 未显式出现在自治策略允许列表。
- 策略处于 disabled 或 shadow-only 且请求真实执行。
- 当前时间不在维护窗口内。
- 同一 Runbook、目标或 Incident 超过速率限制。
- 熔断器处于 open 状态。
- 最近成功率低于策略阈值。
- 关联 Incident、Finding 或参数缺少明确目标。

所有拒绝都必须生成可读的中文原因和稳定英文 reason code。LLM 不能决定是否自动执行；LLM 只能参与可读摘要，策略层和确定性证据决定自治准入。

## 6. 自治模型

新增 `datasentry.autonomy` 包，包含以下模型：

| 模型 | 作用 |
|---|---|
| `AutonomyPolicy` | 单个 Runbook 的自治策略，包含 enabled、shadow_mode、风险限制、维护窗口、速率限制、成功率阈值和熔断阈值 |
| `MaintenanceWindow` | 可执行时间窗口，使用 UTC 星期与分钟范围，避免依赖本地时区 |
| `RateLimitRule` | 针对 Runbook、目标和 Incident 的时间窗口限制 |
| `CircuitBreakerState` | 熔断状态：closed、open、half_open |
| `AutonomyDecision` | 候选评估结果：allowed、shadowed、blocked、escalated |
| `AutonomyRunRecord` | 一次自治候选或执行记录，关联 runbook、operation、incident、decision 和统计字段 |

第一版内置策略只允许：

- `mock.restart_preview`
- `mock.clear_cache_preview`

两者默认 `enabled=false`、`shadow_mode=true`。用户必须显式打开策略后，mock 自动执行才会发生。

## 7. 数据流

告警或人工触发进入自治控制层：

```text
Incident / Finding / manual trigger
→ AutonomyCandidate
→ AutonomyPolicyEngine.evaluate()
→ AutonomyDecision
→ shadow record 或 block/escalate record
→ allowed 时调用 RunbookOperationService.request()
→ RunbookOperationService.approve(actor="datasentry-autonomy")
→ RunbookOperationService.execute(actor="datasentry-autonomy")
→ AutonomyRunRecord 写入最终结果
```

关键约束：

- shadow、blocked、escalated 都不调用 approve/execute。
- allowed 执行必须关联 Operation，并保留 M6 审计事件。
- 自治层额外记录自身决策，不能把 M6 审计事件当成唯一解释来源。
- 执行结束后根据 Operation 状态更新成功率和熔断状态。

## 8. 策略评估

策略评估顺序固定，便于测试和解释：

1. 策略存在且 enabled。
2. Runbook 存在且启用。
3. 执行模式为 `mock`。
4. 风险等级在允许集合内。
5. 当前时间在维护窗口内。
6. 熔断器未 open。
7. 速率限制未超限。
8. 最近统计满足最小样本与成功率阈值。
9. 参数包含目标，且幂等键可渲染。
10. shadow 模式返回 `shadowed`，非 shadow 返回 `allowed`。

任一失败返回 `blocked` 或 `escalated`：

- 策略 disabled、风险越界、执行模式不安全、熔断 open：`blocked`。
- 维护窗口外、成功率样本不足、速率限制命中：`escalated`，建议走 M6 人工审批。

## 9. 维护窗口与时间

维护窗口全部使用 UTC 存储。API 和前端可以展示本地说明，但后端判断只用 UTC，避免部署环境时区差异。

第一版默认窗口：

- 周一到周五。
- UTC 01:00 到 10:00。
- shadow 模式可以全天评估，但必须在 decision 中标记 `window_matched=false`。

非 shadow 自动执行必须命中维护窗口。

## 10. 速率限制

第一版提供三类计数：

- `per_runbook`: 同一 Runbook 在窗口内最多 N 次。
- `per_target`: 同一 Runbook + target 在窗口内最多 N 次。
- `per_incident`: 同一 Incident 在窗口内最多 N 次自动执行。

计数只统计 `allowed` 且已创建 Operation 的记录。shadow 记录用于分析，不消耗真实自动执行额度。

## 11. 熔断

熔断器按 Runbook 维护：

- `closed`: 正常评估。
- `open`: 禁止自动执行，直接升级人工审批。
- `half_open`: 只允许一条 mock 自动执行探测，通过后关闭，失败后重新 open。

打开条件：

- 最近窗口内连续失败达到阈值。
- 操作后验证失败达到阈值。
- 执行异常、锁冲突或策略内部错误达到阈值。

关闭条件：

- 人工 reset。
- half_open 探测成功。

M7 第一版不自动从 open 进入 half_open，必须由 API 或 CLI 显式操作，避免无人值守恢复。

## 12. 存储

新增 SQLite 迁移，保存：

- `autonomy_policies`
- `autonomy_runs`
- `autonomy_circuit_breakers`
- `autonomy_rate_counters`

所有 payload 使用统一脱敏能力。记录中允许保存 runbook 名称、目标别名、Incident id、Operation id、decision code、中文摘要、统计数字和 UTC 时间；不保存 secret、命令正文、连接串、环境变量或未脱敏工具输出。

## 13. API

新增接口：

- `GET /api/autonomy/policies`
- `GET /api/autonomy/policies/{runbook_name}`
- `PATCH /api/autonomy/policies/{runbook_name}`
- `POST /api/autonomy/evaluate`
- `POST /api/autonomy/execute`
- `GET /api/autonomy/runs`
- `GET /api/autonomy/stats`
- `POST /api/autonomy/circuit-breakers/{runbook_name}/reset`

`POST /api/autonomy/evaluate` 只返回决策，不创建 Operation。`POST /api/autonomy/execute` 在 shadow 或策略未允许时只记录决策，不执行；只有 `allowed` 才会创建、批准并执行 mock Operation。

## 14. React 控制台

在现有审批页面增加“自治”区域，首版展示：

- 策略开关和 shadow 状态。
- 每个 Runbook 的维护窗口、速率限制、成功率和熔断状态。
- 最近自治决策列表。
- 一键 evaluate mock 候选。
- 仅在 mock 且策略允许时提供 execute 按钮。

页面仍只访问 DataSentry API，不直连生产组件。

## 15. 测试策略

后端测试覆盖：

- 策略 disabled、shadow、allowed、blocked、escalated。
- 维护窗口命中和未命中。
- L2/L3、forbidden、非 mock 执行模式被拒绝。
- 速率限制和熔断。
- allowed 路径复用 M6 服务并记录 Operation。
- shadow 路径不创建 Operation。
- 存储迁移和 Repository 读写。
- API schema、错误码和脱敏。

前端测试覆盖：

- TypeScript 类型检查。
- 构建成功。
- 自治区域能渲染策略、统计和决策。

最终验证：

```bash
.venv/bin/ruff format --check .
.venv/bin/ruff check .
.venv/bin/mypy src
.venv/bin/pytest tests -q -W error::ResourceWarning --cov=datasentry --cov-report=term-missing --cov-fail-under=90
cd frontend && npm run typecheck
cd frontend && npm run build
```

## 16. 云端实例策略

M7 本地控制层开发不需要开启云端实例。

需要云端或测试环境的情况仅包括：

- 补跑真实 Alertmanager 到 DataSentry API 的只读 smoke。
- 在明确维护窗口中人工审批执行一种低风险真实 Runbook。
- 收集真实执行成功率、失败原因和审计样本。
- M7 后期判断某个 Runbook 是否具备从 shadow 转为有限自治的依据。

在这些条件满足前，M7 不能声称已经具备生产自治能力。

## 17. 退出标准

M7 第一版代码退出标准：

- 本地 mock 自治控制层完整可用。
- 默认策略为 disabled + shadow，不会意外执行。
- 开启 mock 策略后，allowed 路径能自动创建、批准、执行并验证 Operation。
- 所有 blocked、escalated、shadowed 决策有可审计原因。
- 速率限制、维护窗口和熔断均有测试保护。
- React 控制台能查看策略、统计和最近决策。
- 自动化验证通过。

M7 生产自治评估退出标准另行满足：

- 至少一种低风险 Runbook 已在测试环境和维护窗口中多次人工审批成功。
- 专用最小权限执行用户落地。
- 真实执行器、回滚或恢复方案、操作后验证和审计全部通过复核。
- 成功率和适用条件可量化。
- 任何异常结果都会立即停止并通知用户。
