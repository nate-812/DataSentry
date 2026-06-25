# DataSentry 项目状态

> 本文档是跨线程、跨窗口和跨阶段协作的项目交接面板。开始工作前先读取本文档；发生阶段变化、范围调整、重要决策、阻塞、风险或计划外变更时及时更新。

## 当前快照

| 项目 | 当前状态 |
|---|---|
| 总体状态 | M0 工程基础已合并到 `main`，尚未推送 GitHub |
| 当前阶段 | M0：工程规范完善 |
| 当前工作 | 语言规范调整已完成，等待合并和推送 |
| 下一里程碑 | 推送 M0 后启动 M1 知识驱动诊断 |
| 生产权限 | 尚未接入生产服务器；只读工具和写操作均未实现 |
| 默认分支 | `main` |
| 远端仓库 | `https://github.com/nate-812/DataSentry.git` |
| 最近状态更新时间 | 2026-06-25 |

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

## 正在进行

- 已在 `refactor/chinese-user-facing-text` 完成语言规范和现有代码中文化调整。

## 下一步

1. 合并语言调整分支到本地 `main`。
2. 推送本地 `main` 并确认 GitHub CI。
3. 创建 M1 详细实施计划。

## 阻塞与风险

### 当前阻塞

- 无。

### 已知风险

- 本地 `main` 尚未推送 GitHub，远端仍缺少 M0 实现和语言规范调整。
- 生产连接方式、只读账号和监控组件尚未进入实现阶段。
- `/root/bin` 运维脚本尚未完成源码级审计，不能进入自动执行白名单。
- Kafka Consumer Group 不可见原因、真实保留策略和部分 Doris/Flink 配置仍需后续现场确认。

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
| M0 工程基础 | 已合并本地 `main`，待推送 | 项目骨架、领域模型、SQLite、CLI、测试和 CI |
| M1 知识驱动诊断 | 未开始 | 知识路由、血缘模型和确定性规则 |
| M2 真实只读工具 | 未开始 | 接入 Flink、API、主机、Kafka、Doris、Redis/MySQL 和有限日志 |
| M3 监控看板与通知 | 未开始 | Prometheus、Grafana、Alertmanager 和消息渠道 |
| M4 对话与 Web | 未开始 | FastAPI Agent、可插拔 LLM 和 React 控制台 |
| M5 事件记忆与 RCA | 未开始 | Incident 生命周期、历史检索和复盘 |
| M6 审批式自动运维 | 未开始 | Runbook、审批、执行、审计和验证 |
| M7 有限自治 | 未开始 | 对长期验证的低风险操作开放自动执行 |

## 关键文档

- [总体架构与开发路线](superpowers/specs/2026-06-25-datasentry-overall-architecture-design.md)
- [M0 工程基础实施计划](superpowers/plans/2026-06-25-m0-engineering-foundation.md)
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
