# DataSentry 项目状态

> 本文档是跨线程、跨窗口和跨阶段协作的项目交接面板。开始工作前先读取本文档；发生阶段变化、范围调整、重要决策、阻塞、风险或计划外变更时及时更新。

## 当前快照

| 项目 | 当前状态 |
|---|---|
| 总体状态 | M2 真实只读工具已完成并创建 Draft PR；等待评审、CI 和合并 |
| 当前阶段 | M2：PR 评审收尾 |
| 当前工作 | M2 功能分支已推送，Draft PR #2 已创建；Kline 端到端只读影子巡检、Kafka Consumer Group 和 MySQL 规则表固定样本复测均通过；MySQL 异常表根因仍需安全复盘 |
| 下一里程碑 | 评审并合并 M2 PR #2；合并后从最新 `main` 创建 M3 分支开始监控看板与通知 |
| 生产权限 | 已执行固定 HTTP GET、固定 SSH 白名单命令和固定数据库/Redis 只读探测；测试实例临时使用 root key，生产方案仍必须使用专用只读用户；写操作未实现 |
| 默认分支 | `main` |
| 远端仓库 | `https://github.com/nate-812/DataSentry.git` |
| 最近状态更新时间 | 2026-06-26 |

## 已完成

- 整理 StreamLake-Binance 系统、部署、数据血缘、可靠性、应用和运维知识库。
- 明确第一版边界：主题知识加载、白名单只读查询、SQLite 巡检快照、证据化诊断和缺失组件提醒。
- 建立 Git 仓库并连接 GitHub。
- 在 `AGENTS.md` 固化 Git、安全、工程质量和运维权限规则。
- 完成并批准 DataSentry 总体架构与 M0～M7 开发路线。
- 确定技术方向：开源可观测性底座 + 自研领域 Agent。
- 完成 Python 3.12+ 工程骨架、配置、结构化日志和统一异常体系。
- 完成 Observation、Evidence、Finding、Incident、Operation 领域模型。
- 完成 SQLite 迁移、Repository、模拟巡检 CLI 和 GitHub CI。
- CLI 可创建模拟巡检，并将巡检、观察和结论写入 SQLite 后读回。
- 完成 `knowledge/INDEX.md` 解析、1～3 份主题知识加载和路径安全校验。
- 完成数据不更新、组件宕机、延迟/反压和配置问题的确定性路由。
- 完成 Collector → Kafka → Flink → Doris/Redis/API 的显式血缘与检查路径。
- 完成首批确定性规则、历史证据隔离、诊断编排和本地模拟诊断 CLI。

## 正在进行

- M2 本地代码与自动测试已完成，已开始云端只读契约探测。
- Flink Jobs、Job 详情、Checkpoint、Backpressure 固定 REST 探测通过。
- Spring API `/actuator/health` 与 `/api/kline/latest` 固定 GET 探测通过；现场发现 latest 可返回空数组，已补契约 fixture 与解析兼容。
- AI Engine `/health` 固定 GET 探测通过，当前为 RUNNING normal。
- SSH known_hosts 已由用户核对，测试实例临时使用 root key 执行固定白名单只读命令；三台主机资源、时间同步和固定服务指纹探测通过。
- Kafka 进程指纹为 RUNNING；实际 bootstrap 为 `data1:9092` 或 `192.168.1.10:9092`，Topic 列表、broker 状态和 `binance.trade.raw` Offset 推进探测通过。
- Kafka Consumer Group `flink-kline-group` 的 `FIND_COORDINATOR` 问题已由用户修复：单节点新版 Kafka 内部 Topic 副本配置不匹配且最初修改了错误启动配置文件；`__consumer_offsets` 创建后 Coordinator 恢复，固定 group 工具复测为 `VISIBLE` 并可读取 lag。
- Doris 使用 root 无密码连接 `streamlake` 库成功；`kline_1min`、`whale_alert`、`risk_trigger` 和 `ai_diagnosis` 固定新鲜度查询通过，现场字段差异已固化到固定查询测试。
- Kline 端到端只读影子巡检通过：Inspection `completed`，9 个工具调用全部 `succeeded`，结论为“K线主链路当前正在推进”；关键事实包括 Kafka Topic 推进、Kline Job RUNNING、Checkpoint 连续失败 0、Backpressure ok、Doris 新鲜度约 1 分钟。
- MySQL root 可连接 `risk_control`；用户手工补回 `risk_rules` 和 `whale_thresholds` 后，固定样本工具复测通过；异常表名 `RECOVER_YOUR_DATA_info` 的根因仍未确认。
- Redis 使用 ACL 用户 `default` 后固定只读样本工具通过。
- `spring_api` 有限日志路径已确认并通过固定日志工具验证：`/opt/StreamLake-Binance/api-server/api.log`。

## 下一步

1. 评审并合并 [M2 Draft PR #2](https://github.com/nate-812/DataSentry/pull/2)，未经用户确认不自动合并。
2. 合并后从最新 `main` 创建 M3 分支，开始 Prometheus、Grafana、Alertmanager 和消息渠道设计与实现。
3. 人工复盘 MySQL `risk_control` 表异常原因，尤其是 `RECOVER_YOUR_DATA_info` 的来源、root 暴露面、备份和访问日志。
4. 如果页面仍显示 K 线不更新，继续检查 Spring API 查询参数、缓存和前端轮询；本轮主链路证据显示 Collector → Kafka → Flink → Doris 正在推进。

## 阻塞与风险

### 当前阻塞

- 无代码实现阻塞；剩余为 PR 评审/合并与生产安全复盘。

### 已知风险

- 尚未现场确认 GitHub CI 对当前 `main` 的最近一次运行结果。
- 当前 SSH 使用 root 仅因用户确认实例可丢弃；生产或长期实例必须切换到无 sudo、无写权限的只读用户。
- MySQL `risk_control` 曾出现异常表名并丢失业务表，存在数据被异常改动或库名误配风险；业务表虽已手工补回，根因仍需安全复盘。
- `/root/bin` 运维脚本尚未完成源码级审计，不能进入自动执行白名单。
- Kafka 真实保留策略和部分 Doris/Flink 配置仍需后续现场确认。

## 已确认的关键决策

| 决策 | 结论 |
|---|---|
| 产品形态 | 自动运维 Agent + 可视化看板 + 消息提醒 + 对话入口 |
| 建设方式 | 不购买商业 AIOps；采用开源底座并自研 StreamLake 领域智能 |
| 可观测性 | Prometheus、Grafana、Alertmanager；Loki/Alloy 后续接入 |
| Agent 后端 | Python / FastAPI，核心诊断与具体 LLM 解耦 |
| LLM 策略 | 本地 Ollama 优先；确定性规则优先，模型不可用时仍能巡检 |
| 存储 | SQLite 起步，出现多用户或并发写入需求后迁移 PostgreSQL |
| 自动化 | 先只读诊断，再审批式 Runbook，最后仅开放经过验证的有限自治 |
| 安全边界 | 禁止任意 Shell、自动补数、自动 Savepoint 恢复、自动改生产配置和删除数据 |

## 阶段进度

| 阶段 | 状态 | 目标 |
|---|---|---|
| 总体设计 | 已完成 | 架构、边界、安全模型和路线获得确认 |
| M0 工程基础 | 已完成 | 项目骨架、领域模型、SQLite、CLI、测试和 CI |
| M1 知识驱动诊断 | 已完成 | 知识路由、血缘模型和确定性规则 |
| M2 真实只读工具 | 本地实现完成，云端契约探测进行中 | 接入 Flink、API、主机、Kafka、Doris、Redis/MySQL 和有限日志 |
| M3 监控看板与通知 | 未开始 | Prometheus、Grafana、Alertmanager 和消息渠道 |
| M4 对话与 Web | 未开始 | FastAPI Agent、可插拔 LLM 和 React 控制台 |
| M5 事件记忆与 RCA | 未开始 | Incident 生命周期、历史检索和复盘 |
| M6 审批式自动运维 | 未开始 | Runbook、审批、执行、审计和验证 |
| M7 有限自治 | 未开始 | 对长期验证的低风险操作开放自动执行 |

## 关键文档

- [总体架构与开发路线](superpowers/specs/2026-06-25-datasentry-overall-architecture-design.md)
- [M0 工程基础实施计划](superpowers/plans/2026-06-25-m0-engineering-foundation.md)
- [M1 知识驱动诊断实施计划](superpowers/plans/2026-06-25-m1-knowledge-driven-diagnosis.md)
- [M2 真实只读工具实施计划](superpowers/plans/2026-06-25-m2-real-readonly-tools.md)
- [M2 当前交接与剩余事项](M2_HANDOFF.md)
- [知识导航](../knowledge/INDEX.md)
- [Agent 接入与查询规范](../knowledge/09-agent-integration.md)
- [工程协作规则](../AGENTS.md)

## 变更日志

### 2026-06-25

- 创建项目知识库并完成 GitHub 初始化。
- 确认采用“Prometheus/Grafana/Alertmanager 开源底座 + DataSentry 自研领域 Agent”。
- 批准总体架构、运行闭环、安全分级和 M0～M7 开发顺序。
- 创建本项目状态文档，并要求后续在阶段变化、重要决策、阻塞和变故发生时及时维护。
- 起草 M0 工程基础详细实施计划，明确文件结构、测试、验证命令和八个提交检查点。
- M0 工程基础实施计划通过评审，进入实施准备。
- 在 `feat/m0-engineering-foundation` 完成 M0 实现：Python 工程、领域模型、SQLite Repository、CLI、测试和 CI。
- 全量测试期间发现 SQLite 迁移连接未关闭；增加回归测试并修复，资源警告现作为测试错误处理。
- M0 保持本地模拟边界，未接入生产服务器、LLM、FastAPI 或 Web。
- 确认工程语言边界：所有技术标识符使用英文；注释、用户提示、异常 message 和业务说明使用中文；技术名词保留英文原名。
- 将语言与命名规则浓缩写入 `AGENTS.md`，并中文化现有 docstring、CLI 帮助、异常 message、业务文本和脱敏提示；机器契约保持英文。
- 起草 M1 知识驱动诊断详细实施计划，明确知识索引解析、确定性路由、显式血缘、规则引擎、模拟诊断 CLI、测试和九个提交检查点。
- 在 `feat/m1-knowledge-diagnosis` 完成 M1：知识索引、问题路由、显式血缘、四条确定性规则、诊断编排、模拟 Observation fixtures 和诊断 CLI。
- M1 保持本地模拟边界，未接入生产服务器、LLM、FastAPI、Web 或任何写操作。
- M1 已通过 Pull Request #1 合并到 `main`，本地 `main` 与 `origin/main` 同步。
- 起草 M2 真实只读工具详细实施计划，明确 Inspection 原子生命周期、工具审计、目标与秘密分离、统一脱敏、固定 HTTP/SSH/数据库/Redis 工具、失败隔离、契约测试和生产只读影子验收。
- 创建 `feat/m2-real-readonly-tools` 隔离工作区并通过 M2 实施前基线验证：75 个测试通过，覆盖率 90.49%，Ruff 与 mypy 通过。
- 完成 Inspection 原子生命周期、工具调用审计、目标与秘密分离、统一脱敏和白名单工具网关。
- 完成受控 HTTP、SSH、MySQL、Redis 传输，以及 Flink、API、主机、Kafka、Doris、MySQL、Redis 和有限日志适配器。
- 完成确定性工具计划、局部失败隔离、真实巡检服务和 `inspection run` CLI。
- M2 本地全量验证通过：159 个测试通过，覆盖率 90.25%，Ruff 与 mypy 通过；尚未执行云端现场验证。

### 2026-06-26

- 启动 M2 云端只读契约探测，使用用户本机映射的 `data1`、`data2`、`data3` 主机名整理 ignored `config/targets.toml`，未提交真实目标配置。
- Flink REST 首轮现场探测通过：`streamlake-kline-aggregation`、`streamlake-whale-cep` 和 `streamlake-risk-control` 均为 RUNNING；Kline Checkpoint 连续失败数为 0。
- 现场发现 Flink Backpressure 新版响应使用 `backpressureLevel` 和 `ok`，补充契约 fixture 并兼容聚合结果。
- Spring API 首轮现场探测通过；现场发现 `/api/kline/latest` 可返回空数组，补充契约 fixture 并将空数组识别为有效空结果。
- AI Engine `data1:8000` 重新放通后，`/health` 固定 GET 探测通过，返回 RUNNING normal。
- 用户核对 SSH host key 后，临时使用可丢弃测试实例 root key 执行固定 SSH 白名单命令；三台主机资源、时间同步和固定服务指纹探测通过。
- 现场发现 Ubuntu `df -i --output=...` 不兼容，改为可移植 `df -i`；同时跳过 inode 使用率为 `-` 的行。
- Kafka bootstrap 已改为配置化；现场使用 `data1:9092` 后 Topic 列表、broker 状态和 `binance.trade.raw` Offset 推进探测通过，Consumer Group 查询仍因 `FIND_COORDINATOR` 超时保持未知。
- 继续探测时确认当前执行环境缺少 `DATASENTRY_DORIS_PASSWORD`、`DATASENTRY_MYSQL_PASSWORD` 和 `DATASENTRY_REDIS_PASSWORD`；Doris/MySQL/Redis 未触网，并补充 MySQL/Redis secret 缺失返回 `tool.configuration` 的回归测试。
- `spring_api` 有限日志固定文件读取返回 `tool.upstream_error`，未使用自由 Shell 或自由日志路径，需后续确认真实日志源。
- 按用户提示使用同一临时测试密码做进程内注入后，Doris `kline_1min`、MySQL `risk_rules` 和 `whale_thresholds` 固定工具均返回 `tool.authentication_failed`；Redis `risk:blacklist:*` 固定工具返回 `tool.timeout`。
- Redis 现场超时暴露 redis-py 懒连接异常未归一问题，已补充命令级异常归一和回归测试，后续 Redis 超时稳定返回 `tool.timeout`。
- MySQL 协议握手诊断确认 Doris/MySQL 均为 1045，已补充连接阶段 1044/1045 到 `tool.authentication_failed` 的归一和回归测试。
- 日志 stderr 诊断使用同一个固定 `tail` 白名单命令，确认当前 `spring_api` 文件日志路径不存在。
- 用户确认后将 ignored 目标配置临时切换为 root/default 探测：Redis 改用 ACL 用户 `default` 后固定样本工具通过，`spring_api` 日志路径确认为 `/opt/StreamLake-Binance/api-server/api.log` 并通过固定日志工具验证。
- MySQL root 可连接 `risk_control`，但预期 `risk_rules`、`whale_thresholds` 均不存在，当前仅看到异常表 `RECOVER_YOUR_DATA_info`；未读取该表内容，需人工核查数据库状态或备份。
- 用户确认 Doris root 无密码后，修复数据库目标可省略 `password_env` 的契约；Doris 实际库名为 `streamlake`，不是 `default`。
- Doris 固定新鲜度查询已改用数据库会话 `NOW()` 与业务时间列比较，避免将本地业务时间误判为 UTC clock skew。
- Doris 现场字段差异已确认并修正：`whale_alert.alert_time`、`ai_diagnosis.create_time`；`kline_1min`、`whale_alert`、`risk_trigger` 和 `ai_diagnosis` 新鲜度查询均通过。
- MySQL `risk_control.risk_rules` 和 `risk_control.whale_thresholds` 固定样本查询稳定返回 `tool.configuration`，底层为 1146 表不存在；当前仍未读取 `RECOVER_YOUR_DATA_info` 内容。
- Kline 端到端只读影子巡检成功持久化，Inspection `f8a6243a-1db9-4722-bb48-9beb9958b86d` 为 `completed`，9/9 工具调用成功；Spring API `/api/kline/latest` 当前返回有效空结果，应在后续 API/前端排查中继续确认。
- 用户修复 Kafka 单节点内部 Topic 副本配置与实际启动配置文件后，`flink-kline-group` 固定 group 工具复测通过：Consumer Group 为 `VISIBLE`，lag 可读取。
- 用户手工补回 MySQL `risk_rules` 与 `whale_thresholds` 后，固定样本工具复测通过；代码兼容现场列名 `risk_rules.max_single_qty` 与 `whale_thresholds.threshold_quote`，统一输出为 `threshold`。
- M2 功能分支 `feat/m2-real-readonly-tools` 已推送到 GitHub；首次 `gh pr create` 曾因本机 GitHub CLI 未登录失败。
- 本机 GitHub CLI 登录后已创建 [M2 Draft PR #2](https://github.com/nate-812/DataSentry/pull/2)，当前等待评审、CI 和用户确认合并。
