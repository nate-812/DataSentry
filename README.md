# DataSentry

DataSentry 是面向 StreamLake-Binance 的证据驱动智能运维 Agent。当前 M1
提供知识索引、确定性路由、显式血缘、规则诊断、SQLite 持久化和本地模拟 CLI。

> M1 的诊断只读取仓库知识和本地模拟 Observation，不连接生产服务器，也不执行任何生产写操作。

## 本地开发

要求 Python 3.12 或 3.13：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

## M0 CLI

升级本地数据库：

```bash
datasentry db upgrade --database-path /tmp/datasentry.db
```

创建一次模拟巡检：

```bash
datasentry inspection simulate \
  --database-path /tmp/datasentry.db \
  --question "M0 模拟巡检"
```

读取巡检：

```bash
datasentry inspection show INSPECTION_ID \
  --database-path /tmp/datasentry.db
```

模拟输出包含 `production_access: false`，用于明确表示没有查询生产系统。

## M1 本地知识诊断

使用固定模拟 Observation 诊断“K线不更新”：

```bash
datasentry inspection diagnose \
  --question "为什么K线不更新" \
  --observations-file tests/fixtures/diagnosis/kline_job_missing.json \
  --knowledge-root knowledge \
  --database-path /tmp/datasentry-m1.db
```

输出包含：

- 问题类型与实际加载的 1～3 份主题知识。
- Collector → Kafka → Flink → Doris/API 的有序检查链路。
- 模拟 Observation、确定性 Finding、证据、未知项和建议。
- 可通过 `datasentry inspection show INSPECTION_ID` 读回的 SQLite 巡检记录。

fixture 只模拟现场 Observation。Markdown 知识用于稳定背景和历史引用，不代表当前运行事实；真实 Flink、Kafka、Doris、Redis、MySQL、主机和日志查询属于 M2。

## 配置

| 环境变量 | 默认值 | 用途 |
|---|---|---|
| `DATASENTRY_DATABASE_PATH` | `var/datasentry.db` | SQLite 数据库路径 |
| `DATASENTRY_LOG_LEVEL` | `INFO` | 日志级别 |
| `DATASENTRY_LOG_FORMAT` | `json` | `json` 或 `console` |
| `DATASENTRY_ENVIRONMENT` | `development` | `development`、`test` 或 `production` |

真实秘密不得写入 `.env`、日志、SQLite、命令输出或 Git。

## 验证

```bash
ruff format --check .
ruff check .
mypy src
pytest tests -q -W error::ResourceWarning \
  --cov=datasentry \
  --cov-report=term-missing \
  --cov-fail-under=90
```

## 知识库接入

Agent 新会话按顺序读取：

1. [`knowledge/INDEX.md`](knowledge/INDEX.md)
2. [`knowledge/09-agent-integration.md`](knowledge/09-agent-integration.md)
3. 根据索引只加载当前问题相关的 1～3 份主题文档

实时状态必须通过受限只读工具现场查询；历史快照不能包装成当前事实。

## 设计文档

- [`项目当前状态`](docs/PROJECT_STATUS.md)
- [`DataSentry 总体架构与开发路线设计`](docs/superpowers/specs/2026-06-25-datasentry-overall-architecture-design.md)
- [`M0 工程基础实施计划`](docs/superpowers/plans/2026-06-25-m0-engineering-foundation.md)
- [`M1 知识驱动诊断实施计划`](docs/superpowers/plans/2026-06-25-m1-knowledge-driven-diagnosis.md)
