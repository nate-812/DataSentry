# DataSentry 项目状态

> 本文档是跨线程、跨窗口和跨阶段协作的项目交接面板。开始工作前先读取本文档；发生阶段变化、范围调整、重要决策、阻塞、风险或计划外变更时及时更新。

## 当前快照

| 项目 | 当前状态 |
|---|---|
| 总体状态 | M7 有限自治本地控制层已完成阶段性实现 |
| 当前阶段 | M7：有限自治本地 mock/shadow 闭环已实现 |
| 当前工作 | M7 已完成自治策略模型、策略评估、SQLite 记录、自治服务、FastAPI API 和 React 控制台；StreamLake Git 合并与上一实例云端 smoke 已收尾；用户已将该云端实例打镜像并释放，当前无在线云端进程 |
| 下一里程碑 | 新会话从本地/GitHub `main` 作为事实来源继续开发；如需继续云端验证，先从镜像新建实例、更新公网 IP 映射，再只读 smoke |
| 生产权限 | 上一可丢弃实例曾执行固定 HTTP GET、固定 SSH 白名单命令和固定数据库/Redis 只读探测；当前实例已释放，不存在可操作云端；生产方案仍必须使用专用只读用户，写操作未实现 |
| 默认分支 | `main` |
| 远端仓库 | `https://github.com/nate-812/DataSentry.git` |
| 最近状态更新时间 | 2026-07-01 |

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
- 完成 M2 真实只读工具、工具审计、受控传输、真实巡检编排和现场只读契约验证，并通过 Pull Request #2 合并到 `main`。
- 完成 M3 仓库内监控与通知基线：Prometheus 规则、Alertmanager 路由模板、Grafana dashboard、Alertmanager payload 解析、通知消息格式、本地模拟 CLI 和自监控指标。
- 完成 M4 对话与 Web 控制台：FastAPI Agent、Chat API/SSE、Alertmanager API、OpenAI-compatible LLM 摘要、React Command Center、证据查看和本地模拟审批。
- 完成 M6 审批式自动运维：Runbook 领域模型、SQLite 审计与锁、幂等、策略、mock 执行器、操作后验证、FastAPI API 和 React 审批操作台。

## 正在进行

- M7 有限自治本地控制层已实现；首版仍保持 Mock/本地受控执行器边界，真实生产写操作不在本地开发范围内。
- M5 已合并到 `main`；真实云端 Alertmanager smoke 尚未执行，因开发验证不要求打开云实例。
- MySQL 异常表 `RECOVER_YOUR_DATA_info` 的根因仍需安全复盘，但不阻塞 M5 设计和仓库内工程启动。
- 2026-06-30 已在可丢弃云实例上复跑 K 线真实只读巡检：主机、Collector、Kafka、Flink、Doris 和 Spring API 探测均成功；确认真实 Spring K 线接口为 `/api/kline/{symbol}?interval=1min&limit=...`，DataSentry 探针已从旧 `/api/kline/latest` 修正。
- 2026-06-30 已按用户授权在可丢弃云实例上轮换 MySQL `root` 与 Redis `default` 密码，并通过 root-only `/root/.streamlake-secrets` 注入 StreamLake 作业运行环境；仓库文档和配置不保存真实密码。
- 改密后已重启 `streamlake-whale-cep` 与 `streamlake-risk-control`，并确认 `streamlake-kline-aggregation`、`streamlake-whale-cep`、`streamlake-risk-control` 均为 RUNNING；Doris 仍按现场事实保持 root 无密码，MySQL 密码不控制 Doris 登录。
- 真实改密巡检发现 Flink REST 会同时返回同名历史 CANCELED 作业和当前 RUNNING 作业；DataSentry 已修正为优先选择运行中作业，避免旧历史作业污染当前状态判断。
- StreamLake-Binance `feature/frontend-realtime-dashboard` 已合并到 GitHub `main`，merge commit 为 `9123d01`；其中改密源码提交为 `3fdf9bb`，只包含 Flink job 从环境变量读取 MySQL/Redis 密码的源码改动。
- 云端 `/opt/StreamLake-Binance` 已切换并同步到 `main...origin/main`；改密回滚备份已移出 Git 仓库到 `/root/streamlake-local-backups/20260630-password-rotation/`，云端只剩 `ai-engine/docker-compose.yml`、`ai-engine/nohup.out` 和 `ai-engine/volumes/` 三类未跟踪现场运行文件。
- 2026-06-30 已将云端 `/opt/StreamLake-Binance` fast-forward 到 GitHub `main` 的 `8033d63`，未重启服务；`ops/bin` 与 `ops/checks` 只读 smoke 通过，三条 Flink Job、Spring API、AI Engine、Kafka Topic、Redis 黑名单、MySQL 风控规则和 Doris freshness 均可查询。
- 2026-07-01 用户说明：上一云端实例已打镜像并释放，当前没有任何云端进程运行；2026-06-30 的云端 smoke 仅作为历史验收证据，不能再当作当前在线状态。

## 下一步

1. 新会话继续项目时，以本地/GitHub `main` 为事实来源；新改动使用新分支，本地开发验证后推送 GitHub，再由云端只执行部署拉取。
2. 视需要创建 M7 PR，并在后续只读 smoke、测试环境和维护窗口中收集低风险 Runbook 人工审批执行样本。
3. 如需要，先从镜像新建云实例并更新 `data1` 公网 IP 映射，再执行 Alertmanager fixture 或真实 Alertmanager 到 DataSentry API 的只读 smoke；不做任何生产写操作。
4. 在具备 macOS 自动化窗口调整权限的环境补跑 M4/M5 移动宽度截图 QA。
5. 人工复盘 MySQL `risk_control` 表异常原因，尤其是 `RECOVER_YOUR_DATA_info` 的来源、root 暴露面、安全组、备份和访问日志；确认云端 root-only 改密备份文件无需回滚后可删除。
6. 如果页面仍显示 K 线不更新，优先检查前端是否调用 `/api/kline/{symbol}?interval=1min&limit=...`，以及页面缓存、轮询和 symbol 选择；2026-06-30 现场证据显示 Collector → Kafka → Flink → Doris → Spring API 主链路正在推进。

## 阻塞与风险

### 当前阻塞

- 无代码实现阻塞。

### 已知风险

- M3 合并后尚未进行真实部署验收；当前仅确认仓库内实现、PR checks 和本地验证。
- 上一云端实例已释放，当前无在线进程；任何 `data1` 公网 IP、SSH host key、云端 smoke 和进程状态都需要在新实例创建后重新确认。
- 上一实例 SSH 使用 root 仅因用户确认实例可丢弃；生产或长期实例必须切换到无 sudo、无写权限的只读用户。
- MySQL `risk_control` 曾出现异常表名并丢失业务表，存在数据被异常改动或库名误配风险；MySQL/Redis 已轮换密码并拒绝无密码访问，但根因、入口来源、安全组和访问日志仍需安全复盘。
- 云端 `/root/bin` 和 StreamLake 作业源码的改密前备份文件仅 root 可读，短期用于回滚；其中仓库内 `.bak` 文件已移到 `/root/streamlake-local-backups/20260630-password-rotation/`，确认运行稳定后应删除这些包含旧默认密码的备份。
- 云端 StreamLake 仓库已同步到 `main`，但 `ai-engine/docker-compose.yml`、`ai-engine/nohup.out` 和 `ai-engine/volumes/` 仍是未跟踪现场运行文件；后续应迁移到仓库外运行目录或明确纳入 `.gitignore`，避免云端工作区再次变脏。
- `/root/bin` 运维脚本尚未完成源码级审计，不能进入自动执行白名单。
- Kafka 真实保留策略和部分 Doris/Flink 配置仍需后续现场确认。
- StreamLake 云端 smoke 发现 Doris freshness 延迟榜中个别交易对存在数十分钟延迟，最高样本为 `IMXUSDT` 约 69 分钟；需后续确认是否与风控黑名单、源数据活跃度或作业处理有关。
- M3 目前只完成仓库内模板和本地模拟，尚未真实部署 Prometheus、Grafana、Alertmanager，尚未发送真实企业微信或 Webhook 消息。
- M5 已通过本地自动化验证，但尚未在云实例上执行真实 Alertmanager → DataSentry API smoke。

## 已确认的关键决策

| 决策 | 结论 |
|---|---|
| 产品形态 | 自动运维 Agent + 可视化看板 + 消息提醒 + 对话入口 |
| 建设方式 | 不购买商业 AIOps；采用开源底座并自研 StreamLake 领域智能 |
| 可观测性 | Prometheus、Grafana、Alertmanager；Loki/Alloy 后续接入 |
| Agent 后端 | Python / FastAPI，核心诊断与具体 LLM 解耦 |
| LLM 策略 | OpenAI-compatible API key 优先；确定性规则优先，模型不可用时仍能巡检 |
| 存储 | SQLite 起步，出现多用户或并发写入需求后迁移 PostgreSQL |
| 自动化 | 先只读诊断，再审批式 Runbook，最后仅开放经过验证的有限自治 |
| 安全边界 | 禁止任意 Shell、自动补数、自动 Savepoint 恢复、自动改生产配置和删除数据 |

### M4 已选设计方向

| 主题 | 当前选择 |
|---|---|
| 控制台布局 | Command Center：概览与聊天并重，事件、证据、审批和 Grafana 为一级入口 |
| Agent API | FastAPI，聊天诊断任务通过 SSE 推送进度 |
| LLM 接入 | OpenAI-compatible API key 优先，同时保留 Mock 和 disabled 降级 |
| LLM 边界 | 只做可读总结，不选择工具、不判定权限、不生成生产写操作 |
| 审批页面 | 本地模拟审批状态流，可批准/拒绝模拟操作，不接生产 Runbook |
| Web 边界 | React 控制台只访问 DataSentry API，不直连生产组件 |
| 前端实现 | React + TypeScript + Vite + 普通 CSS；首版不引入状态管理框架 |

## 阶段进度

| 阶段 | 状态 | 目标 |
|---|---|---|
| 总体设计 | 已完成 | 架构、边界、安全模型和路线获得确认 |
| M0 工程基础 | 已完成 | 项目骨架、领域模型、SQLite、CLI、测试和 CI |
| M1 知识驱动诊断 | 已完成 | 知识路由、血缘模型和确定性规则 |
| M2 真实只读工具 | 已完成并合并 | 接入 Flink、API、主机、Kafka、Doris、Redis/MySQL 和有限日志 |
| M3 监控看板与通知 | 已完成并合并 | Prometheus、Grafana、Alertmanager 和消息渠道 |
| M4 对话与 Web | 已完成并合并 | FastAPI Agent、可插拔 LLM 和 React 控制台 |
| M5 事件记忆与 RCA | 已完成并合并 | Incident 生命周期、历史检索和复盘 |
| M6 审批式自动运维 | 已完成并合并 | Runbook、审批、执行、审计和验证 |
| M7 有限自治 | 本地 mock/shadow 闭环已实现 | 对长期验证的低风险操作开放自动执行 |

## 关键文档

- [总体架构与开发路线](superpowers/specs/2026-06-25-datasentry-overall-architecture-design.md)
- [M0 工程基础实施计划](superpowers/plans/2026-06-25-m0-engineering-foundation.md)
- [M1 知识驱动诊断实施计划](superpowers/plans/2026-06-25-m1-knowledge-driven-diagnosis.md)
- [M2 真实只读工具实施计划](superpowers/plans/2026-06-25-m2-real-readonly-tools.md)
- [M3 监控看板与通知设计](superpowers/specs/2026-06-26-m3-observability-notifications-design.md)
- [M4 对话式 Agent 与 Web 控制台设计](superpowers/specs/2026-06-27-m4-dialog-web-console-design.md)
- [M5 事件记忆与 RCA 设计](superpowers/specs/2026-06-28-m5-incident-memory-rca-design.md)
- [M6 审批式自动运维设计](superpowers/specs/2026-06-28-m6-approval-runbooks-design.md)
- [M7 有限自治设计](superpowers/specs/2026-06-29-m7-limited-autonomy-design.md)
- [M3 监控看板与通知实施计划](superpowers/plans/2026-06-26-m3-observability-notifications.md)
- [M4 对话式 Agent 与 Web 控制台实施计划](superpowers/plans/2026-06-27-m4-dialog-web-console.md)
- [M5 事件记忆与 RCA 实施计划](superpowers/plans/2026-06-28-m5-incident-memory-rca.md)
- [M6 审批式自动运维实施计划](superpowers/plans/2026-06-28-m6-approval-runbooks.md)
- [M7 有限自治实施计划](superpowers/plans/2026-06-29-m7-limited-autonomy.md)
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
- 本机 GitHub CLI 登录后创建 [M2 PR #2](https://github.com/nate-812/DataSentry/pull/2)，经用户确认已合并到 `main`。
- 从最新 `main` 创建 M3 分支 `codex/m3-observability-notifications`。
- 用户批准 M3 先做仓库内配置与集成代码，不直接上服务器部署；通知主模板采用企业微信机器人，并保留通用 Webhook 抽象。
- 起草 M3 监控看板与通知设计，范围包括 Prometheus 规则、Grafana dashboard、Alertmanager 模板、Alertmanager payload 解析、诊断消息格式和 DataSentry 自监控指标。
- M3 设计文档通过用户评审，开始起草实施计划，计划按 TDD 拆分通知解析、消息格式、自监控指标、监控模板、CLI 模拟和最终验证。

### 2026-06-27

- 按 M3 实施计划完成 `datasentry.notifications`：解析 Alertmanager Webhook、生成稳定告警去重 key、映射诊断问题，并输出企业微信 Markdown 与通用 Webhook JSON。
- 补充通知安全回归：诊断异常和 Finding unknowns 在进入公开 `NotificationContent` 前即完成脱敏，避免 token、password、Authorization、Cookie 等秘密通过消息对象泄露。
- 完成 `datasentry.observability` 自监控指标内核，可导出 Prometheus text exposition 格式，覆盖工具调用、巡检、通知和失败计数。
- 新增 `monitoring/` 模板：Prometheus scrape 示例与 StreamLake 告警规则、Alertmanager 路由/抑制/企业微信占位 receiver、Grafana provisioning 与六个 dashboard JSON。
- 修正 Alertmanager 示例路由语义，确保 critical 告警既进入 DataSentry，也能继续路由到企业微信占位 receiver；补充 Spring API 和 AI Engine 示例 scrape job。
- 新增 `datasentry notification simulate` CLI，可用本地 Alertmanager fixture 输出企业微信 Markdown 或通用 Webhook JSON；SQLite Repository 生命周期已通过 `enter → run → exit` 回归测试保护。
- M3 分支 `codex/m3-observability-notifications` 已推送到 GitHub；尚未真实部署或发送真实通知。
- 创建 [M3 PR #3](https://github.com/nate-812/DataSentry/pull/3)；首次 GitHub `quality` 因 `ruff format --check .` 失败，涉及 `src/datasentry/cli/app.py` 和 `tests/unit/monitoring/test_monitoring_assets.py`，已提交 `style: 格式化M3变更` 修复。
- M3 PR #3 新一轮 GitHub checks 已通过：`quality` pass，`secrets` pass。
- M3 PR #3 已合并到 `main`，合并提交为 `40b5a41`；本地 `main` 已 fast-forward 同步到 `origin/main`。
- M3 仍保持仓库内基线边界：尚未真实部署 Prometheus、Grafana、Alertmanager，尚未发送真实企业微信或 Webhook 消息。
- 启动 M4 设计；用户选择完整 Web 控制台首版、Command Center 布局和本地模拟审批流。LLM 首版改为 OpenAI-compatible API key 优先，同时保留 Mock 与 disabled 降级，不默认依赖本地 Ollama。
- 完成 M4 实施计划，按 TDD 拆分运行配置、聊天领域模型、SQLite 持久化、LLM Provider、摘要器、模拟审批、ChatService、FastAPI API、Alertmanager API、React 控制台、文档和最终验证。
- 创建 M4 隔离工作区与功能分支 `codex/m4-dialog-web-console`；基线验证通过：`ruff format --check`、`ruff check`、`mypy src` 和全量 pytest 覆盖率门槛。
- 完成 M4 运行配置：新增 FastAPI/Uvicorn 依赖，补充 API、CORS、Grafana 与 LLM 配置；`DATASENTRY_LLM_API_KEY` 只从环境读取且不出现在配置 repr。
- 完成聊天领域模型与 SQLite `0003_chat_console` 迁移，包含 chat session、message、run、run event；失败 run 必须包含非空错误信息，非失败 run 不允许错误字段。
- 完成 Repository 与 SQLite 聊天持久化接口：Inspection/Incident/Operation 列表、聊天会话/消息/任务/事件保存和读取；新增列表查询统一限制 `1..100`，避免 SQLite `LIMIT -1` 无界读取；`ChatRun` 更新只允许修改状态、关联巡检、错误和结束时间。
- 完成可插拔 LLM Provider：disabled、mock、OpenAI-compatible；OpenAI-compatible 调用 `/chat/completions`，发送 Bearer API key 与标准 payload。LLM 上游异常统一映射为脱敏 `LLMProviderError`，并清理 `__cause__` 与 `__context__`，避免 traceback 或调试工具泄露 API key 和上游正文。
- 完成 Answer Summarizer：先生成确定性中文证据摘要，LLM 可用且返回非空内容时使用模型回答；disabled、空内容或 provider 异常时安全降级，不暴露 provider 错误详情。
- 完成本地模拟审批服务：只处理 `simulate_` 前缀 Operation，可在 SQLite 中推进本地 approve/reject 状态，不执行生产 Runbook。
- 完成 ChatService：保存聊天会话、用户消息、诊断 run、助手回答和有序事件；失败时记录 failed run 与安全失败事件。
- 完成基础 FastAPI API：`/api/health` 不泄露 LLM API key，`/api/overview` 返回 Command Center 基础段，Evidence/Incident/Operation 读取和本地模拟 approve/reject 可用；每个请求独立打开并关闭 SQLite Repository。
- 完成 Chat API 与 SSE 回放：支持创建/列出/读取会话，提交同步诊断 run，读取 run 状态，并以 `text/event-stream` 回放已保存事件。
- 完成 Alertmanager API：`POST /api/alertmanager/webhook` 复用 M3 Alertmanager payload 解析并返回 accepted 摘要。
- M4 当前验证快照：全量 `pytest tests -q -W error::ResourceWarning --cov=datasentry --cov-report=term-missing --cov-fail-under=90` 通过，246 个测试通过，覆盖率 91.46%。FastAPI `TestClient` 当前有 StarletteDeprecationWarning，不影响 ResourceWarning 门槛。

### 2026-06-28

- 完成 React Command Center 前端脚手架：`frontend/` 使用 React、TypeScript、Vite 和 lucide-react，`VITE_DATASENTRY_API_BASE` 默认指向本地 DataSentry API。
- 完成控制台核心页面：概览、对话诊断、Incident、证据、模拟审批和 Grafana 入口；页面只访问 DataSentry API，不直连生产组件。
- 完成前端 API client 与类型定义，覆盖 health、overview、chat、SSE 回放、evidence、incidents、operations 和本地模拟 approve/reject。
- M4 前端验证快照：`cd frontend && npm run typecheck` 通过，`cd frontend && npm run build` 通过。构建产物 `frontend/dist/`、`frontend/node_modules/` 和 `frontend/tsconfig.tsbuildinfo` 均保持 ignored。
- M4 LLM 选择已落地为 OpenAI-compatible API key 优先，同时保留 mock 和 disabled 降级；不默认依赖本地大模型。LLM 只做可读摘要，不选择工具、不判断权限、不生成生产写操作。
- M4 最终自动化验证通过：`.venv/bin/ruff format --check .`、`.venv/bin/ruff check .`、`.venv/bin/mypy src`、`.venv/bin/pytest tests -q -W error::ResourceWarning --cov=datasentry --cov-report=term-missing --cov-fail-under=90`、`cd frontend && npm run typecheck`、`cd frontend && npm run build` 均通过；pytest 为 246 个测试通过，覆盖率 91.46%。
- M4 API smoke 使用 FastAPI `TestClient` 进程内验证通过：`/api/health`、`/api/overview`、`POST /api/chat/sessions`、`POST /api/operations/simulations` 分别返回 200、200、201、201。
- M4 桌面浏览器 smoke QA 通过：使用本机 Chrome 打开 `http://127.0.0.1:5173/`，验证概览页 `API ok / LLM mock`、对话诊断提交和 SSE 事件回放、证据页按 inspection id 查询 Finding、审批页创建并批准 `simulate_restart_preview` 本地模拟 Operation。
- 真实浏览器 QA 发现并修复本地 CORS 默认来源问题：Vite 默认打开 `http://127.0.0.1:5173`，后端默认 CORS 原先只允许 `http://localhost:5173`；现已默认同时允许 `localhost` 和 `127.0.0.1`。
- 移动宽度截图 QA 未完成：调整 Chrome 窗口的 `osascript` 调用受 macOS 自动化权限卡住；CSS 响应式规则仍已随前端 build/typecheck 覆盖，后续在具备窗口调整权限的环境补跑实际移动截图。
- M4 功能分支 `codex/m4-dialog-web-console` 已推送到 GitHub，并创建 [M4 PR #4](https://github.com/nate-812/DataSentry/pull/4)。
- M4 PR #4 已合并到 `main`，合并提交为 `2699c12`；本地 `main` 已 fast-forward 同步到 `origin/main`。M4 仍有一个非阻塞后续验证项：在具备 macOS 自动化窗口调整权限的环境补跑移动宽度截图 QA。
- 启动 M5 设计；用户选择完整闭环方案，并确认 Alertmanager Webhook 作为自动创建和合并 Incident 的主要入口。M5 首版将覆盖 Incident 生命周期、时间线、历史相似事件检索、RCA 草稿和 Markdown 导出，但仍不执行生产写操作、不引入 RAG、不读取 MySQL 异常表内容。
- M5 设计通过用户评审；确认开发阶段不需要打开云实例，可用本地 SQLite、Alertmanager fixture、模拟诊断和前端构建完成主要验证，云实例仅作为末尾可选只读 smoke。
- 起草 M5 实施计划，按 TDD 拆分 Incident 记忆模型、SQLite 持久化、fingerprint/lifecycle/search、RCA、IncidentService、FastAPI API、React 事件工作台、文档和最终验证。
- 创建 M5 功能分支 `codex/m5-incident-memory-rca`，完成 Incident 记忆领域模型、事件关联、时间线、fingerprint、RCA 报告和 upsert 结果模型。
- 新增 SQLite `0004_incident_memory` 迁移和 Repository 持久化接口，覆盖 Incident link、timeline、fingerprint 和 RCA report。
- 完成 Alertmanager 告警指纹、Incident 生命周期推进、历史相似事件排序和确定性 RCA Markdown 草稿生成；历史事件仅作为经验参考，当前事实仍必须来自本次只读巡检证据。
- 完成 IncidentService，将 Alertmanager Webhook 接入自动建档/合并 Incident、关联诊断结果、写入时间线、检索相似事件并生成 RCA。
- 完成 M5 API：`POST /api/alertmanager/webhook` 返回 Incident upsert 结果，新增 Incident 详情、时间线、相似事件、RCA 生成和 Markdown 导出接口。
- 完成 React Incident 工作台，支持状态/严重级别筛选、Incident 详情、时间线、关联证据、相似事件、RCA 预览和 Markdown 导出。
- 为避免循环依赖，将通用脱敏能力拆到 `datasentry.redaction`，`datasentry.tools.redaction` 保留兼容导出。
- M5 最终自动化验证通过：`.venv/bin/ruff format --check .`、`.venv/bin/ruff check .`、`.venv/bin/mypy src`、`.venv/bin/pytest tests -q -W error::ResourceWarning --cov=datasentry --cov-report=term-missing --cov-fail-under=90`、`cd frontend && npm run typecheck`、`cd frontend && npm run build` 均通过；pytest 为 262 个测试通过，覆盖率 91.36%。
- M5 云实例 smoke 未执行：本地开发和自动化验证不需要打开云实例，后续如需可在只读边界内补跑 Alertmanager → DataSentry API smoke。
- M5 功能分支 `codex/m5-incident-memory-rca` 已推送到 GitHub，并创建 [M5 Draft PR #5](https://github.com/nate-812/DataSentry/pull/5)；`secrets` 与 `quality` checks 均通过。
- M5 PR #5 已合并到 `main`，合并提交为 `38fe943`；本地 `main` 已 fast-forward 同步到 `origin/main`。
- M5 合并后在 `main` 重新完成自动化验证：`.venv/bin/ruff format --check .`、`.venv/bin/ruff check .`、`.venv/bin/mypy src`、`.venv/bin/pytest tests -q -W error::ResourceWarning --cov=datasentry --cov-report=term-missing --cov-fail-under=90`、`cd frontend && npm run typecheck`、`cd frontend && npm run build` 均通过；pytest 为 262 个测试通过，覆盖率 91.36%。
- 启动 M6 设计；用户选择 Mock/本地受控执行器优先，先完成 Runbook、审批、审计、幂等、并发锁和操作后验证的本地闭环，不依赖云端实例在线，不执行生产写操作。
- M6 设计通过用户确认；起草 M6 实施计划，按 TDD 拆分 Runbook 领域模型、SQLite 持久化、策略/幂等/锁、mock 执行器、Operation 服务、FastAPI、React 控制台、文档和最终验证。

### 2026-06-29

- M6 后端本地闭环完成阶段性实现：Runbook 领域模型、内置目录、Operation 幂等键、SQLite 审计事件与操作锁、策略校验、mock 执行器、操作后验证和 RunbookOperationService 已落地并提交。
- 完成 M6 FastAPI API：新增 Runbook 目录接口、Runbook Operation 创建/审批/拒绝/执行/取消/事件接口，并保持旧的本地模拟审批入口兼容；缺少必填参数和不存在 Operation 的事件查询已补充回归测试。
- M6 API 阶段验证通过：`tests/integration/api` 14 个测试通过，`ruff check src/datasentry/api src/datasentry/runbooks tests/integration/api` 与 `mypy src/datasentry/api src/datasentry/runbooks` 通过；下一步进入 React 控制台集成。
- 完成 M6 React 审批操作台：支持读取 Runbook 目录、提交 Operation、审批、拒绝、取消、执行和查看审计事件；README 已补充 M6 本地 mock 使用方式和云端边界。
- 当前环境曾因 sandbox 端口监听权限和额度审批限制未完成本地浏览器 smoke；后续以自动化验证为准，必要时在可监听本机端口的环境补跑浏览器 QA。
- M6 最终自动化验证通过：`.venv/bin/ruff format --check .`、`.venv/bin/ruff check .`、`.venv/bin/mypy src`、`.venv/bin/pytest tests -q -W error::ResourceWarning --cov=datasentry --cov-report=term-missing --cov-fail-under=90`、`cd frontend && npm run typecheck`、`cd frontend && npm run build` 均通过；pytest 为 305 个测试通过，覆盖率 91.13%，仅保留 FastAPI TestClient 上游弃用 warning。
- 合并前真实 Uvicorn/Vite 运行暴露 SQLite 请求级连接跨线程使用问题；已补充回归测试并将 SQLite 连接设为 `check_same_thread=False`，最终验证更新为 306 个测试通过、覆盖率 91.13%。
- M6 分支 `codex/m6-approval-runbooks` 已 fast-forward 合并到本地 `main`，M7 可从最新 `main` 启动。
- 从最新 `main` 创建 M7 分支 `codex/m7-limited-autonomy`，完成 M7 有限自治设计与实施计划：首版采用本地 mock/shadow 控制层，不开启云端实例，不执行真实生产写操作。
- 完成 M7 本地有限自治阶段性实现：新增 `datasentry.autonomy` 策略模型、内置策略、策略评估、速率限制升级、SQLite `0007_limited_autonomy` 迁移、自治 run 记录、FastAPI `/api/autonomy/*` API 和 React 审批页自治面板；默认策略仍为 disabled + shadow。
- M7 最终自动化验证通过：`.venv/bin/ruff format --check .`、`.venv/bin/ruff check .`、`.venv/bin/mypy src`、`.venv/bin/pytest tests -q -W error::ResourceWarning --cov=datasentry --cov-report=term-missing --cov-fail-under=90`、`cd frontend && npm run typecheck`、`cd frontend && npm run build` 均通过；pytest 为 333 个测试通过，覆盖率 91.32%，仅保留 FastAPI TestClient 上游弃用 warning。

### 2026-06-30

- StreamLake-Binance GitHub `main` 已合并安全与可运维改造后，云端 `/opt/StreamLake-Binance` 执行 `git pull --ff-only` 同步到 `8033d63`；只执行状态与只读检查，未重启任何服务。
- 云端 smoke 确认：`streamlake-kline-aggregation`、`streamlake-whale-cep`、`streamlake-risk-control` 均为 RUNNING；Spring API `/actuator/health` 为 UP；AI Engine `/health` 为 ok；Kafka Topic、Redis 黑名单、MySQL `risk_rules` 和 Doris `kline_1min` freshness 查询可用。

- 用户开启可丢弃云实例后，更新本机默认 `known_hosts` 和 DataSentry 专用 `datasentry_known_hosts` 中 `data1` 的新实例指纹；将 `datasentry_m2_disposable` 公钥加入 root 后，SSH 只读探测恢复。
- 使用真实云实例复跑 DataSentry K 线只读巡检，Inspection `0e185f0e-ebec-4fc9-b343-51b05b12792a` 确认主机、Collector、Kafka、Flink、Doris 和 Spring API 探测成功，结论为“K线主链路当前正在推进”。
- 现场排查发现当前 Spring API 源码实际暴露 `/api/kline/{symbol}`，旧 `/api/kline/latest` 会被路由解释为 `symbol=latest` 并返回空数组；已修正 DataSentry Spring API 探针为固定只读 `/api/kline/BTCUSDT?interval=1min&limit=1`。
- 修正后再次复跑真实巡检，Inspection `c3e4cee7-0f2b-4fbc-b564-8a7e8fe3fd5f` 中 `api_read_probe.status` 为 `ok`，Doris `kline_1min` 新鲜度约 50 秒。
- 按用户授权在可丢弃云实例上轮换 MySQL `root` 与 Redis `default` 密码；MySQL 无密码 root 已拒绝，Redis 无密码返回 `NOAUTH`，带新密码返回 `PONG`，业务表 `risk_rules=5`、`whale_thresholds=7`。
- 云端 StreamLake 作业源码已改为从环境变量读取 MySQL/Redis 密码，并通过 root-only `/root/.streamlake-secrets` 注入运行环境；`job-whale-cep` 和 `job-risk-control` 模块 Maven 构建通过并重启运行。
- 改密后现场检查确认 `streamlake-kline-aggregation`、`streamlake-whale-cep`、`streamlake-risk-control` 均为 RUNNING，Collector 进程存在，Doris `kline_1min` 新鲜度约几十秒，Spring API 固定 K 线查询返回 1 条。
- 真实巡检发现 Flink REST 同名历史 CANCELED 作业会干扰当前状态选择；DataSentry 已新增回归测试并修正为优先选择 RUNNING 作业，提交 `abc671f fix: 修正Flink同名作业状态选择` 已推送到 DataSentry `main`。
- StreamLake-Binance 改密源码提交 `3fdf9bb fix: 从环境变量读取作业密码` 已推送到 `feature/frontend-realtime-dashboard`，随后用户将该分支合并到 GitHub `main`，merge commit 为 `9123d01`。
- 云端 `/opt/StreamLake-Binance` 已从 `feature/frontend-realtime-dashboard` 切换到 `main` 并同步 `origin/main`；`frontend/package-lock.json` 的现场差异已保存到 `stash@{0}`，两个改密回滚 `.bak` 文件已移出仓库到 `/root/streamlake-local-backups/20260630-password-rotation/`。
- 后续 StreamLake 开发约定为本地开发验证、GitHub 合并、云端只拉取部署；云端不再作为开发工作区，真实秘密继续放在 `/root/.streamlake-secrets`，不进入 Git。
- 云端实例再次打开后执行 DataSentry 只读 K 线巡检，Inspection `b9d03578-aaec-4b93-9d42-3991e76aa18a` 确认 Flink 三个作业均 RUNNING，Kline checkpoint 最近完成且连续失败数为 0，反压为 ok，Doris `kline_1min` 新鲜度约 49 秒，Spring API 固定 K 线查询返回 ok；SSH 类工具本次仍报 `tool.connection_failed`，因此主机、Collector 和 Kafka SSH 证据未闭合。
- 本次安全暴露面初查显示，从当前网络可连接 MySQL `3306`、Redis `6379`、Flink Web `8081`、Spring API `8080`、AI Engine `8000`、Doris FE `9030/8030`；Kafka `9092` 拒绝连接。MySQL root 无密码被拒绝，Redis 无密码返回 `NOAUTH`，但 Doris `9030` 仍可用 root 无密码执行只读查询，需优先收口安全组或账号权限。
- 本地 FastAPI M5 Alertmanager fixture smoke 通过：`POST /api/alertmanager/webhook` 返回 200 并创建 Incident `4d0261d3-8108-4ae9-8183-154f4f18ef00`，Incident 详情、时间线、相似事件、RCA 生成和 Markdown 导出接口均返回 200；仅保留 FastAPI TestClient 上游弃用 warning。
- 运行事实补查确认 Flink REST 当前生效配置包括 RocksDB state backend、30s checkpoint、保留 3 个 checkpoint、`RETAIN_ON_CANCELLATION`、JM/TM bind-host 为 `0.0.0.0`；Doris 为 data1 FE + data2/data3 BE，`kline_1min` 为 `UNIQUE KEY(symbol, open_time)`、8 bucket、单副本、merge-on-write。Flink `/jobmanager/config` 会返回 OSS access key id 且仅掩码 secret，公网可读状态需视为安全风险。
- 本地 M7 有限自治 API smoke 通过：`mock.restart_preview` 启用 shadow 后执行返回 `shadowed` 并记录自治 run；关闭 shadow 后因当前 UTC 时间超出默认维护窗口返回 `escalated`/`policy.maintenance_window_missed`，未创建 Operation，符合维护窗口拦截预期。
- 用户确认新实例 `data1` 公网 IP `8.216.92.30` 的新 SSH host key 后，本机 DataSentry 专用 known_hosts 已加入该 IP；SSH 不再使用 `data1` 主机名，避免本机代理拦截。data1 可通过内网免密转接 data2/data3。
- 已在 data1 创建 OS 用户 `datasentry-readonly`，仅属于自身用户组、无 sudoers 文件、密码登录已锁定，并复用当前巡检公钥；该用户可执行主机基础只读命令和 Kafka `data1:9092` Topic 只读查询。
- 已创建并验证 MySQL、Redis 和 Doris 的 `datasentry_readonly` 只读账号；本地 ignored `config/targets.toml` 已临时切换到公网 IP、`datasentry-readonly` 和三个 `datasentry_readonly` 数据账号。使用这些只读身份执行 DataSentry K 线巡检，Inspection `b856a02e-9061-4b76-a2a2-b4a6fec97616` 完成且结论为“K线主链路当前正在推进”。
- Redis `datasentry_readonly` ACL 已限制为巡检所需读命令和 `risk:blacklist:*` 范围，并通过 `CONFIG REWRITE` 持久化；MySQL `datasentry_readonly` 仅授予 `risk_control.*` 的 `SELECT, SHOW VIEW`；Doris `datasentry_readonly` 仅授予 `streamlake.*` 的 `SELECT_PRIV`。
- Doris root 改密暂缓：Flink 三个 Job 源码默认 Doris `root` 空密码，运行中 sink 重连可能受影响；`job.sh` 会加载 `/root/.streamlake-secrets`，但 `spring.sh` 和 `ai.sh` 当前未 source 该文件。Doris root 改密需与 DORIS 环境变量注入、Spring/AI 脚本修正和 Flink Job 维护窗口重启一起执行。
- 本机未安装或未配置云厂商 CLI（`aliyun`/`aws`/`gcloud`/`az` 均不可用），因此本次未直接修改云安全组；公网端口暴露风险仍需在云控制台或配置好 CLI 后收口。
- 已确认旧改密备份未被 `/root/bin` 或 StreamLake 仓库引用，并删除 `/root/bin/job.sh.bak-20260630-password-rotation`、`/root/streamlake-local-backups/20260630-password-rotation/RiskControlJob.java.bak-20260630-password-rotation`、`/root/streamlake-local-backups/20260630-password-rotation/WhaleCepJob.java.bak-20260630-password-rotation`；复查无剩余旧改密备份文件。

### 2026-07-01

- 用户说明上一云端实例已在 2026-06-30 smoke 后打镜像并释放；当前没有任何云端进程运行，后续云端验证必须从新实例、公网 IP、SSH host key 和只读账号连通性重新开始。
