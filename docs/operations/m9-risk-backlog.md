# M9 风险 Backlog

本文档跟踪 M9 后续维护风险。它服务于本地准备和下次 `data1` 维护窗口，不替代现场只读查询，不把历史 smoke 包装为当前事实。

## 使用方式

- 不开云端实例时，只做本地梳理、文档补充、测试保护和维护窗口准备；不执行 SSH，不访问生产端口，不修改云安全组，不打印真实 secret。
- 开云端后，先按 `docs/operations/m9-exposure-maintenance-plan.md` 做只读确认，再逐项更新本 backlog。
- 每个条目只记录脱敏证据、状态、ID 和下一步；不记录密码、token、Cookie、私钥、完整连接串或业务敏感样本。
- 任何生产写操作、账号变更、systemd 变更、云安全组变更、Doris root 改密或 Runbook 权限扩大，都必须单独确认。

## 风险分级

| 优先级 | 含义 | 处理原则 |
|---|---|---|
| P0 | 已影响生产链路或暴露核心入口 | 需要维护窗口优先处理，处理前明确回滚方案 |
| P1 | 安全暴露面或可恢复性风险较高 | 下次云端打开后优先只读确认，随后按组件收口 |
| P2 | 可观测性、文档、脚本或运维卫生风险 | 云端不开时可先准备检查表、测试和迁移计划 |
| P3 | 长期改进或低频风险 | 收敛为后续阶段候选项，不阻塞 M9 收口 |

## 当前 Backlog

| ID | 优先级 | 风险 | 当前证据 | 本地准备 | 云端只读验证 | 升级条件 | 关闭条件 |
|---|---|---|---|---|---|---|---|
| M9-R1 | P1 | 既有公网监听仍待收口 | 状态文档记录 MySQL、Redis、AI Engine、Flink Web、Spring API、Doris FE 仍存在 `0.0.0.0` 或 `*` 监听风险 | 维护预案已拆分组件顺序；checklist 已加入自启动、监听、账号和回归证据 | 只读记录监听、云安全组入口和组件 health；每次只处理一个组件 | 任一核心组件仍可公网访问，或收口后业务 health 失败 | 组件入口改为 loopback、内网或 SSH tunnel，且 M9 回归通过 |
| M9-R2 | P1 | `get_kafka_topic` 对 `data1` 返回 `tool.timeout` | M9 真实巡检 9 个工具调用中 8 个 succeeded，`get_kafka_topic` 为 `tool.timeout` | 梳理 Kafka CLI timeout 的候选原因：broker 响应慢、命令环境限制、只读账号 PATH 或网络抖动 | 复跑固定 Kafka Topic 只读工具，记录耗时、退出码和脱敏 stderr | 连续复现 timeout，或影响 K 线链路确认 | Kafka Topic 工具稳定 succeeded，或有明确降级说明和替代证据 |
| M9-R3 | P1 | Doris root 改密与写入账号治理未完成 | Doris 仍按现场事实存在 root 相关历史，Doris root 改密已明确放入单独维护窗口 | 梳理 Spring、Flink、AI Engine 对 `DORIS_USER`、`DORIS_PASSWORD` 的依赖和回滚点 | 只读确认 Doris 用户、权限、Flink Job 状态、Spring API K 线读探针和 Doris freshness | 发现 root 仍公网可用、写入账号缺失或改密会中断业务 | 专用写入账号和只读账号边界清楚，root 改密窗口完成并通过回归 |
| M9-R4 | P2 | AI Engine 运行方式不统一 | M9 固定只读确认显示 AI Engine systemd 单元 inactive，但 8000 `/health` 为 ok，说明仍由既有进程方式运行 | 准备进程来源记录模板，区分 systemd、nohup、docker compose 和手工进程 | 只读确认 `systemd` 状态、进程命令、8000 监听和 `/health` | AI Engine 无法自动恢复，或进程来源不明 | 明确运行方式并纳入受控启动、日志和回滚记录 |
| M9-R5 | P2 | 本地 SSH known_hosts 指纹管理需清理 | 本地 ignored `config/targets.toml` 临时改用默认 known_hosts；专用 `datasentry_known_hosts` 中 `data1` 指纹已过期 | 准备指纹核验步骤，不在仓库记录真实主机指纹 | 用户核对真实指纹后更新本机专用 known_hosts，并复跑只读 SSH 白名单命令 | 指纹不匹配或只能用默认 known_hosts 绕过 | `datasentry_known_hosts` 恢复可用，目标配置不再依赖临时默认路径 |
| M9-R6 | P2 | 云端 AI Engine 未跟踪运行文件仍留在仓库目录 | 状态文档记录 `ai-engine/docker-compose.yml`、`ai-engine/nohup.out`、`ai-engine/volumes/` 仍是云端未跟踪现场运行文件 | 本地准备迁移方案：移到仓库外运行目录，或明确纳入 `.gitignore` | 云端只读 `git status --short`，确认未跟踪文件范围和是否包含 secret | 未跟踪文件包含 secret，或污染云端 Git 工作区影响部署 | 运行文件迁出仓库或被清晰忽略，云端工作区干净 |
| M9-R7 | P2 | `/root/bin` 运维脚本已完成源码初审但不得自动执行 | 基于用户提供的 `root_bin_audit_report.md` 已完成源码初审；发现 root 无密 SSH、root 权限运行应用、`job.sh` 缺乏幂等性、`ai.sh` 监听 `0.0.0.0:8000`、旧备份脚本残留等阻断项 | 已形成 `docs/operations/root-bin-script-audit.md`；继续保持脚本不进入 DataSentry 自动执行白名单 | 下次开云端后只读列出 `/root/bin` 文件清单、权限、mtime 和哈希，确认是否与报告一致，不执行脚本 | 发现脚本内容变化、仍由 root 长期运行业务服务、或脚本打印 secret | 云端只读复核完成，脚本迁移或标注为人工维护工具；未通过脚本保持禁止自动执行 |
| M9-R8 | P2 | Doris freshness 个别交易对延迟需解释 | 云端 smoke 曾发现 `IMXUSDT` 等个别交易对 freshness 延迟数十分钟 | 准备区分源数据活跃度、黑名单、Flink 处理和 Doris 写入延迟的只读检查顺序 | 只读采样 Doris freshness、Kafka offset、Flink checkpoint 和 API 固定读 | 延迟扩大到主交易对或影响告警准确性 | 延迟原因明确，规则阈值或观测说明已更新 |
| M9-R9 | P1 | MySQL `RECOVER_YOUR_DATA_info` 异常来源未完全复盘 | 当前表名已未查到，但历史出现过异常表和业务表缺失风险 | 整理访问日志、安全组、备份和 root 暴露面复盘模板 | 只读确认表清单、账号权限、MySQL 错误日志和安全组事实 | 异常表复现、业务表缺失或 root 仍暴露 | 入口来源和影响范围明确，账号和暴露面收口完成 |

## 不开云端时可推进

- 维护 `docs/operations/m9-exposure-maintenance-plan.md` 和 `docs/operations/production-exposure-checklist.md`，让下次维护窗口可照单执行。
- 为本 backlog 补充测试，确保关键风险不从文档入口中消失。
- 准备证据记录模板、只读验证顺序和回滚边界。
- 将每个 P1/P2 风险拆成“本地准备”和“开云端后的只读验证”，避免云端打开后临场决策。
- 保持生产写边界：不自动修改生产配置，不开放生产写 Runbook，不把任何脚本加入自动执行白名单。

## 开云端后的只读验证

下次 `data1` 打开后，按以下顺序更新 backlog：

1. 记录 `datasentry-api` 与 `datasentry-alertmanager-proxy.socket` 的 `systemctl is-enabled` 和 `systemctl is-active`。
2. 只读确认监听、云安全组、Prometheus/Grafana/Alertmanager loopback 状态。
3. 对 Flink Web、Doris FE、MySQL、Redis、Spring API、AI Engine 分别记录当前状态和回归结果。
4. 复跑 `datasentry ops preflight`、`datasentry monitoring deployment-check`、`datasentry monitoring alert-smoke` 和 `datasentry inspection run`。
5. 只记录 Incident id、Inspection id、状态和脱敏摘要。

## 退出条件

M9 风险 backlog 可以收口到维护状态的条件：

- P1 风险均有当前现场证据、处理结论和关闭条件。
- 公网监听入口已收口，或每个暂缓项都有用户确认的风险接受说明。
- DataSentry API、监控 smoke、Alertmanager 回调和 K 线真实只读巡检在维护窗口后通过。
- secret、SSH 指纹、云端未跟踪运行文件和 `/root/bin` 脚本都有明确边界。
- 生产写 Runbook、自动重启、自动补数、自动改配置和自动 Savepoint 恢复仍未开放。
