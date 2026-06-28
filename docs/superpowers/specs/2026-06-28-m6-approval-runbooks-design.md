# M6 审批式自动运维设计

## 1. 背景

DataSentry 已完成真实只读巡检、监控通知、对话控制台、Incident 记忆和 RCA。M6 的目标是把“可建议操作”升级为“可审批、可审计、可验证的 Runbook 操作”，但第一版仍不执行生产写操作。

本设计选择 Mock/本地受控执行器优先。它先完成 Runbook、审批、执行审计、并发锁、幂等和操作后验证的完整工程闭环，为后续接入 Ansible、专用执行用户和真实低风险修复打基础。

## 2. 目标

- 定义版本化、参数化 Runbook，包含风险等级、参数 schema、执行模式、预检和验证要求。
- 将现有本地模拟审批升级为正式 Operation 生命周期：请求、等待审批、批准、拒绝、执行、验证、成功、失败或取消。
- 记录操作前检查、审批、执行、输出摘要和操作后验证的审计事件。
- 实现幂等键和并发锁，避免重复请求重复执行或同一目标并发冲突。
- 提供只执行本地 mock 的受控执行器接口，不运行 SSH、Shell、SQL 写入或云端变更。
- 扩展 FastAPI 和 React 控制台，使用户能查看 Runbook、提交 Operation、审批、执行和查看审计详情。

## 3. 非目标

- 不接入 `/root/bin` 真实脚本执行；仅记录脚本审计状态和“未审计不可执行”规则。
- 不接入 Ansible、SSH 写命令、数据库写 SQL、Flink savepoint、补数、配置修改、网络或安全组变更。
- 不实现自动批准或 M7 有限自治。
- 不引入完整登录、SSO、RBAC 或多租户。M6 第一版继续使用请求字段中的 `requester` 和 `approver` 表示操作者身份，并为后续认证保留策略接口。
- 不要求云端实例在线。云端只读 smoke 和真实低风险演练是后续验收项，不阻塞本地开发。

## 4. 安全边界

M6 第一版只允许执行 `mock` 模式 Runbook。任何 `shell`、`ssh`、`sql_write`、`ansible`、`production` 或未知执行模式都必须被策略层拒绝。

禁止操作包括：

- 任意 Shell 命令。
- 数据库写入、删除、DDL 或自由 SQL。
- 自动补数。
- 自动 Savepoint 恢复。
- 生产配置修改。
- 主机网络、SSH、云安全组修改。
- 未完成源码审计的 `/root/bin` 脚本。

所有审计 payload、执行输出和 API 响应必须使用统一脱敏能力处理，不保存 secret、Authorization、Cookie、SSH key、数据库密码、完整连接串、完整环境变量或自由命令文本。

## 5. Runbook 模型

Runbook 是稳定、版本化的操作模板。字段包括：

| 字段 | 含义 |
|---|---|
| `name` | 稳定英文标识，例如 `mock.restart_preview` |
| `version` | 语义化或日期版本，例如 `1.0.0` |
| `title` | 中文展示名 |
| `description` | 中文说明 |
| `risk` | `L0`、`L1`、`L2`、`L3` 或 `forbidden` |
| `execution_mode` | 第一版只允许 `mock` |
| `parameter_schema` | JSON Schema 风格的参数约束 |
| `precheck` | 操作前检查说明和本地 mock 检查配置 |
| `postcheck` | 操作后验证说明和本地 mock 验证配置 |
| `lock_key_template` | 并发锁模板，例如 `runbook:{name}:{target}` |
| `idempotency_key_template` | 幂等键模板，例如 `{name}:{version}:{target}:{incident_id}` |
| `enabled` | 是否可请求 |
| `audit_notes` | 审计说明，例如脚本来源、人工复核要求 |

第一版内置三个 Runbook：

1. `mock.restart_preview`：L1，模拟服务重启预检、执行和验证。
2. `mock.clear_cache_preview`：L1，模拟缓存刷新预检、执行和验证。
3. `forbidden.shell_command`：forbidden，用于证明任意 Shell 被拒绝，不能进入执行阶段。

## 6. Operation 生命周期

Operation 继续复用现有领域模型，并补充服务层状态流。

```text
requested
→ awaiting_approval
→ approved
→ running
→ verifying
→ succeeded
```

拒绝和失败路径：

```text
requested 或 awaiting_approval → rejected
approved 或 running 或 verifying → failed
requested 或 awaiting_approval → cancelled
```

关键规则：

- 请求 Runbook 时先校验参数、风险策略、启用状态和幂等键。
- L1 mock Runbook 默认进入 `awaiting_approval`，不能创建后直接成功。
- `forbidden` Runbook 只能创建失败或被拒绝的审计结果，不能进入 `approved`、`running`、`verifying` 或 `succeeded`。
- 批准只表示允许执行，不等于执行完成。
- 执行成功后必须进入 `verifying`，验证通过后才进入 `succeeded`。
- 审批人不能与请求人相同的规则先作为可配置策略保留；第一版默认允许同名操作者，以兼容本地单人开发和 QA。

## 7. 幂等与并发锁

幂等键用于防止重复请求生成多个待执行 Operation。相同 Runbook、版本、目标、Incident 和关键参数在已有 active Operation 时返回已有 Operation，并记录 `idempotency_reused` 审计事件。

active 状态包括：

- `requested`
- `awaiting_approval`
- `approved`
- `running`
- `verifying`

并发锁用于防止同一目标同时执行冲突操作。锁在进入 `running` 前获取，在 `succeeded`、`failed` 或 `cancelled` 后释放。锁记录至少包含：

- `lock_key`
- `operation_id`
- `runbook_name`
- `target`
- `acquired_at`
- `expires_at`
- `released_at`

锁过期只用于恢复异常中断，不作为自动执行依据。M6 第一版不自动重试执行。

## 8. 审计事件

新增 Operation audit event，用来记录可展示、可追溯的状态变化和关键决策。

事件类型包括：

- `operation_requested`
- `policy_evaluated`
- `idempotency_reused`
- `approval_granted`
- `approval_rejected`
- `execution_started`
- `executor_output_recorded`
- `verification_started`
- `verification_succeeded`
- `verification_failed`
- `operation_failed`
- `operation_cancelled`

每个事件包含：

- `id`
- `operation_id`
- `event_type`
- `summary`
- `actor`
- `payload`
- `created_at`

`payload` 只保存脱敏摘要、稳定状态、目标别名和证据引用，不保存完整命令、secret 或连接详情。

## 9. 执行器

第一版定义执行器接口，但只实现 `MockRunbookExecutor`。

执行器输入：

- Runbook 定义。
- Operation。
- 已验证参数。
- 预检摘要。

执行器输出：

- `status`：`succeeded` 或 `failed`。
- `summary`：中文摘要。
- `details`：脱敏结构化结果。
- `started_at` 和 `finished_at`。

`MockRunbookExecutor` 根据 Runbook 名称和参数返回确定性结果。它不得读取生产配置、不得访问网络、不得运行子进程。

后续真实执行器必须单独设计，至少满足：

- 专用最小权限账号。
- 明确允许列表。
- 参数化命令或 Ansible playbook。
- 超时、中断、回滚或恢复说明。
- 生产只读影子模式。
- 明确维护窗口和人工批准。

## 10. 操作后验证

验证器与执行器分离。M6 第一版实现 `MockOperationVerifier`，读取 Runbook 的 `postcheck` 配置并生成确定性验证结果。

真实验证器后续必须通过 M2 已有只读工具或 Prometheus/Alertmanager 状态查询完成，不能复用执行器输出当作验证事实。

验证结果进入 Operation `result` 和审计事件。验证失败时 Operation 状态为 `failed`，并给出中文失败摘要和后续人工处理建议。

## 11. 存储设计

在现有 `operations` 表基础上新增迁移，优先新增独立表，减少破坏性修改。

新增表：

- `runbooks`：保存内置 Runbook 快照，便于 API 展示和版本审计。
- `operation_events`：保存审计事件。
- `operation_locks`：保存并发锁。

`operations.result_json` 继续保存最终执行和验证摘要。`operations.parameters_json` 继续保存已校验参数。

如果需要幂等查询，可在 `operations.result_json` 或新增列中保存 `idempotency_key`。第一版优先新增显式 `idempotency_key` 列，便于索引和测试。

## 12. API 设计

新增或扩展接口：

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/api/runbooks` | 列出可展示 Runbook |
| `GET` | `/api/runbooks/{name}` | 查看 Runbook 详情 |
| `POST` | `/api/operations` | 基于 Runbook 创建 Operation |
| `GET` | `/api/operations` | 列出 Operation，保留现有行为并扩展字段 |
| `GET` | `/api/operations/{id}` | 查看 Operation 详情 |
| `GET` | `/api/operations/{id}/events` | 查看审计事件 |
| `POST` | `/api/operations/{id}/approve` | 批准 Operation |
| `POST` | `/api/operations/{id}/reject` | 拒绝 Operation |
| `POST` | `/api/operations/{id}/execute` | 执行已批准 Operation |
| `POST` | `/api/operations/{id}/cancel` | 取消未执行 Operation |

兼容接口：

- `/api/operations/simulations` 保留为本地演示入口，但内部应创建 `mock.restart_preview` 或 `mock.clear_cache_preview` Runbook Operation。
- 旧的 approve/reject 前端行为仍能工作，但 approve 后状态将变为 `approved` 或进入完整执行流程，具体由前端更新展示。

## 13. 前端设计

审批页从“模拟 Operation 列表”升级为 Runbook 操作台，包含：

- Runbook 列表和风险标签。
- Operation 创建表单，首版支持 target、reason、incident_id 等有限字段。
- 待审批、已批准、执行中、验证中、成功、失败、拒绝的分组展示。
- Operation 详情区域，展示参数、风险、状态、请求人、审批人、结果和审计事件。
- 批准、拒绝、执行、取消按钮。

界面继续保持 DataSentry Command Center 风格，不直连生产组件。所有操作都调用 DataSentry API。

## 14. 测试策略

单元测试：

- Runbook 参数校验。
- 风险策略拒绝 forbidden 和未知执行模式。
- Operation 状态流。
- 幂等键生成和复用。
- 锁获取、冲突和释放。
- 审计事件脱敏。
- Mock executor 和 verifier 的确定性结果。

集成测试：

- SQLite 迁移和 Repository 读写。
- FastAPI Runbook 列表、Operation 创建、审批、执行、验证、审计事件查询。
- 兼容 `/api/operations/simulations`。

前端验证：

- `npm run typecheck`。
- `npm run build`。
- 本地浏览器 smoke：创建 mock Operation、批准、执行、查看审计事件。

最终验证：

- `ruff format --check .`
- `ruff check .`
- `mypy src`
- `pytest tests -q -W error::ResourceWarning --cov=datasentry --cov-report=term-missing --cov-fail-under=90`
- `cd frontend && npm run typecheck`
- `cd frontend && npm run build`

## 15. 交付边界

M6 第一版交付后，应能在本地完成：

1. 查看版本化 Runbook。
2. 创建低风险 mock Operation。
3. 人工批准或拒绝。
4. 执行已批准 Operation。
5. 执行后独立 mock 验证。
6. 查看完整审计事件。
7. 重复提交不会创建冲突执行。
8. forbidden Runbook 和任意 Shell 能力被明确拒绝。

未完成云端实例 smoke 不阻塞 M6 第一版代码开发；但项目状态文档必须明确记录“未执行真实写操作，云端低风险演练待后续维护窗口”。

## 16. 后续演进

M6 后续子阶段按顺序推进：

1. 审计 `/root/bin` 脚本源码，形成合格、需改写、禁止三类清单。
2. 为合格操作编写真实版本化 Runbook，但保持禁用。
3. 在测试环境接入受控执行器。
4. 生产只读影子模式验证 precheck 和 postcheck。
5. 明确维护窗口后，人工批准执行一种低风险修复。
6. 收集成功率、失败原因和审计样本，为 M7 有限自治做依据。
