# Data Sentry Agent 知识库

StreamLake-Binance 智能运维 Agent 的项目知识已经按领域重新编排。

## 接入入口

新会话或新Agent按顺序读取：

1. [`knowledge/INDEX.md`](knowledge/INDEX.md)
2. [`knowledge/09-agent-integration.md`](knowledge/09-agent-integration.md)
3. 根据索引只加载当前问题相关的主题文档

不要一次加载全部文档。实时状态必须通过只读工具现场查询。

## 知识目录

```text
knowledge/
├── INDEX.md
├── 01-system-overview.md
├── 02-deployment-map.md
├── 03-jobs-and-lineage.md
├── 04-configuration-and-reliability.md
├── 05-application-and-ai.md
├── 06-operations.md
├── 07-runtime-baseline-2026-06-25.md
├── 08-risks-and-unknowns.md
└── 09-agent-integration.md
```

第一版开发范围：主题知识加载、白名单只读查询、SQLite巡检快照和证据化诊断。暂不需要RAG或自动写操作。
