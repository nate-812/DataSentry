# StreamLake-Binance 知识导航

本目录是 StreamLake-Binance 智能运维 Agent 的规范知识库。内容由项目源码调查、云端巡检和运维资料按领域重新编排而成。

## 文档地图

| 文档 | 内容 | 典型问题 |
|---|---|---|
| [01-system-overview.md](01-system-overview.md) | 项目定义、技术栈、模块、整体架构 | “这个项目由什么组成？” |
| [02-deployment-map.md](02-deployment-map.md) | 三台服务器、组件位置、端口、进程和部署方式 | “Kafka在哪台机器、哪个目录？” |
| [03-jobs-and-lineage.md](03-jobs-and-lineage.md) | Collector、三个Flink Job、Topic/表/Key血缘 | “K线为什么不更新？该沿哪条链路查？” |
| [04-configuration-and-reliability.md](04-configuration-and-reliability.md) | 配置优先级、Checkpoint、状态、时间语义、恢复与数据语义 | “这个Job如何恢复？配置从哪里来？” |
| [05-application-and-ai.md](05-application-and-ai.md) | Spring API、WebSocket、AI Engine、现有Milvus实现、前端状态 | “AI模块和API如何工作？” |
| [06-operations.md](06-operations.md) | 构建部署、`/root/bin`脚本、运维权限和操作风险 | “如何检查或启动Flink？” |
| [07-runtime-baseline-2026-06-25.md](07-runtime-baseline-2026-06-25.md) | 2026-06-25三节点运行快照、资源和数据新鲜度 | “上次巡检时系统是什么状态？” |
| [08-risks-and-unknowns.md](08-risks-and-unknowns.md) | 风险、冲突、未知项、待验证事项 | “当前最危险和最不确定的是什么？” |
| [09-agent-integration.md](09-agent-integration.md) | Agent加载、查询、持久化、证据和操作控制规范 | “新Agent该怎么接入这些知识？” |

## 使用原则

1. 当前服务器只读查询结果优先于历史文档。
2. 源码和实际配置优先于规划说明。
3. `07-runtime-baseline-2026-06-25.md`是历史快照，不能当作当前状态。
4. 每次只加载当前问题需要的主题文档，不要一次塞入全部知识。
5. 密码、Token、私钥、Cookie和AK/SK不得持久化或返回。

## 快速路由

| 用户意图 | 必读 | 按需追加 |
|---|---|---|
| 全局架构 | 01 | 02、03 |
| 组件位置/连接 | 02 | 04 |
| 数据延迟/断流 | 03 | 04、07、08 |
| Flink故障 | 03、04 | 02、06、08 |
| Kafka故障 | 02、03 | 04、07、08 |
| Doris/Redis异常 | 02、03 | 04、07、08 |
| API/AI异常 | 05 | 02、04、06 |
| 运维操作 | 06 | 02、04、08 |
| 历史状态对比 | 07 | 对应组件主题文档 |
| Agent开发 | 09 | 01、02、03、06、08 |
