# M9 组件级维护 Runbook

本文档把 M9 风险 backlog 中的 P1/P2 风险拆成组件级人工 runbook。它服务于下次 `data1` 维护窗口；不开云端实例时不执行 SSH、不访问生产端口、不修改云安全组、不读取或打印真实 secret。

## 使用边界

- 每次只处理一个组件，处理完成并通过回归后再进入下一个组件。
- 不自动修改云安全组，不执行未确认的生产写操作，不开放生产写 Runbook。
- 任何 systemd、账号权限、监听地址、云安全组或数据库权限变更，都必须先记录只读证据并获得用户确认。
- 证据记录使用 `docs/operations/maintenance-evidence-record.md`，只写状态、ID、脱敏摘要和失败项。
- 历史 smoke 只能作为背景，不能包装成当前事实。

## 通用执行顺序

1. 确认本轮维护窗口、目标实例、操作者和云端实际 Git commit。
2. 只读记录当前监听、进程、组件 health、账号边界和相关风险 ID。
3. 判断本轮是否允许处理该组件；不允许时写入暂缓原因。
4. 用户确认后只执行该组件的最小变更。
5. 运行组件级回归；失败时只回滚本组件最近一次变更。
6. 记录 Incident id、Inspection id、未验证项和 secret 处理确认。

## Flink Web

关联风险：M9-R1、M9-R8。

| 项目 | 内容 |
|---|---|
| 只读确认 | 记录 Flink Web 监听地址、访问来源、三条当前 Job 状态、checkpoint 连续失败数、backpressure 状态和重启次数。 |
| 变更前证据 | 记录 Flink REST 是否可从受控路径访问，保存脱敏 Job id、状态和失败项，不记录完整日志或 secret。 |
| 允许变更 | 仅在用户确认后收紧公网入口或访问路径；不自动 cancel Job，不自动提交 Savepoint，不自动重提作业。 |
| 回滚边界 | 仅恢复本轮 Flink Web 网络入口或访问规则；不回滚业务数据，不重启 Kafka、Doris、Spring API 或 AI Engine。 |
| 变更后回归 | 复查 Flink REST 可达、三条 Job 为 RUNNING、checkpoint/backpressure 正常，再运行真实 K 线只读巡检。 |
| 暂缓条件 | Job 非 RUNNING、checkpoint 连续失败、只读 REST 不可达或用户未确认网络变更时暂缓。 |

## Doris FE

关联风险：M9-R1、M9-R3、M9-R8。

| 项目 | 内容 |
|---|---|
| 只读确认 | 记录 Doris FE 监听地址、用户清单、DataSentry 只读账号状态、写入账号状态和 `kline_1min` freshness。 |
| 变更前证据 | 记录账号名、权限边界、固定 freshness 查询结果和 Spring/Flink 依赖的变量名，不记录密码值。 |
| 允许变更 | 网络入口收口可以在本轮处理；Doris root 改密必须单独维护窗口，不和暴露面收口混在同一步。 |
| 回滚边界 | 网络收口失败时恢复上一版入口；账号变更失败时按独立改密方案回滚，不删除数据表。 |
| 变更后回归 | 复跑 Doris freshness、Spring API 固定 K 线读探针、Flink Job 状态和 DataSentry 真实只读巡检。 |
| 暂缓条件 | 写入账号缺失、root 改密方案未确认、freshness 异常扩大或 Spring/Flink 依赖不清楚时暂缓。 |

## MySQL

关联风险：M9-R1、M9-R9。

| 项目 | 内容 |
|---|---|
| 只读确认 | 记录 MySQL 监听地址、安全组入口、`risk_control` 表清单、诊断只读账号权限和错误日志摘要。 |
| 变更前证据 | 记录 `risk_rules`、`whale_thresholds` 固定只读样本查询状态，以及 `RECOVER_YOUR_DATA_info` 是否复现。 |
| 允许变更 | 用户确认后只收口网络入口或只读账号权限；不执行任意 SQL，不删除异常表，不修改业务表。 |
| 回滚边界 | 仅恢复本轮网络入口或账号权限调整；不回滚已确认的安全密码轮换。 |
| 变更后回归 | 复跑 MySQL 固定只读样本、DataSentry preflight 和真实 K 线只读巡检中相关步骤。 |
| 暂缓条件 | 异常表复现、业务表缺失、root 暴露面未确认或只读账号权限异常时暂缓。 |

## Redis

关联风险：M9-R1。

| 项目 | 内容 |
|---|---|
| 只读确认 | 记录 Redis 监听地址、安全组入口、ACL 用户状态、计划内只读命令和 `KEYS` 禁止边界。 |
| 变更前证据 | 记录 dbsize、`risk:blacklist:*` 样本 key 数和命令耗时，不记录业务值或 secret。 |
| 允许变更 | 用户确认后只收口网络入口或只读 ACL；不执行写命令，不执行 `KEYS`，不清空 DB。 |
| 回滚边界 | 仅恢复本轮网络入口或 ACL 调整；不回滚密码轮换，不修改业务 key。 |
| 变更后回归 | 复跑 Redis 固定只读采样、DataSentry preflight 和真实只读巡检中相关步骤。 |
| 暂缓条件 | ACL 边界不清、只读采样 timeout、业务依赖账号未确认或用户未确认变更时暂缓。 |

## Spring API

关联风险：M9-R1、M9-R3。

| 项目 | 内容 |
|---|---|
| 只读确认 | 记录 Spring API 监听地址、health、K 线固定读接口、进程用户和 Doris/MySQL/Redis 变量依赖。 |
| 变更前证据 | 记录 `/api/kline/{symbol}?interval=1min&limit=...` 固定读探针和脱敏错误，不记录响应中的敏感业务样本。 |
| 允许变更 | 用户确认后按 `docs/operations/streamlake-service-hardening-plan.md` 收口公网入口或迁移启动方式；不现场编译未验证代码，不自动改数据库连接配置。 |
| 回滚边界 | 恢复上一版入口规则或启动方式，随后复查 API health 和 K 线固定读探针。 |
| 变更后回归 | 复跑 API health、K 线固定读探针、Doris freshness 和 DataSentry 真实只读巡检。 |
| 暂缓条件 | 依赖变量不清、当前进程用户不明、API health 失败或变更需要重新构建产物时暂缓。 |

## AI Engine

关联风险：M9-R1、M9-R4。

| 项目 | 内容 |
|---|---|
| 只读确认 | 记录 AI Engine 8000 监听、`/health`、systemd 状态、进程命令、进程用户和启动来源。 |
| 变更前证据 | 区分 systemd、nohup、docker compose 和手工进程；记录脱敏命令摘要，不记录环境变量值。 |
| 允许变更 | 用户确认后按 `docs/operations/streamlake-service-hardening-plan.md` 收口公网入口或迁移到受控启动方式；不自动拉起 root 进程，不打印模型或 API secret。 |
| 回滚边界 | 恢复上一版入口或进程管理方式，并复查 `/health` 与 DataSentry 固定 HTTP GET。 |
| 变更后回归 | 复查 `/health`、监听地址、DataSentry 固定 HTTP 工具和告警 smoke 中的 RCA 生成链路。 |
| 暂缓条件 | 进程来源不明、systemd 与实际进程冲突、secret 注入边界不清或 health 不稳定时暂缓。 |

## 全局回归

组件处理完成后，至少运行并记录以下结果或暂缓原因：

```bash
datasentry ops preflight --targets-file /etc/datasentry/targets.toml
datasentry monitoring deployment-check --config-file /etc/datasentry/monitoring.toml
datasentry monitoring alert-smoke --config-file /etc/datasentry/monitoring.toml --payload-file tests/fixtures/alertmanager/kline_freshness_firing.json
datasentry inspection run --question "为什么K线不更新" --targets-file /etc/datasentry/targets.toml --knowledge-root knowledge --database-path /var/lib/datasentry/datasentry.db
```

如果任何一步失败，记录失败状态、脱敏 stderr、Incident id 或 Inspection id，并回到对应组件 runbook；不要继续处理下一个组件。
