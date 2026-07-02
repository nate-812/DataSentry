# M9 生产化与安全收口设计

## 1. 文档状态

- 项目：DataSentry
- 阶段：M9 生产化与安全收口
- 日期：2026-07-02
- 状态：已获用户方向确认，作为 M9 实施计划输入
- 主题：DataSentry API 云端本机部署、Alertmanager 自动回调、暴露面收口、secret 与只读账号固化

## 2. 背景

M8 已完成 Prometheus、Grafana 和 Alertmanager 真实部署验收，并通过本地 DataSentry API 完成 Alertmanager payload 到 Incident、timeline、RCA 和 Markdown export 的闭环 smoke。当前缺口不是诊断能力，而是生产形态：

- Alertmanager 配置中的 DataSentry Webhook 仍指向预留云端端口，真实告警不能长期自动进入 DataSentry。
- DataSentry API 仍主要按本地开发或 smoke 方式启动，缺少 systemd、独立运行目录、secret 注入和回归流程。
- 云端公网暴露面、只读账号、known_hosts、secret 文件和监控回归流程需要统一收口。

用户已确认 M9 首轮采用 `data1` 本机部署方案：开发和版本管理仍在本地与 GitHub，云端只运行一个明确版本的 DataSentry API 实例。M9 不是把开发环境搬到服务器，也不是开放生产写操作。

## 3. 目标

1. 设计并实现 DataSentry API 在 `data1` 的受控运行形态：
   - 独立系统用户。
   - 独立源码或发布目录。
   - 独立 SQLite 数据库目录。
   - 独立日志目录。
   - systemd 管理。
   - 只监听 `127.0.0.1`。
2. 将 Alertmanager 的 DataSentry receiver 指向本机回调地址：
   - `http://127.0.0.1:18000/api/alertmanager/webhook`。
   - 回调只进入 DataSentry API，不暴露公网端口。
3. 固化生产 secret 注入方式：
   - 使用云端 root-only 或服务用户可读的环境文件。
   - 文件只保存环境变量，不进入 Git、SQLite、日志、RCA、通知或命令输出。
   - 继续支持 `datasentry ops preflight` 检查 secret 配置状态。
4. 固化只读账号和目标配置边界：
   - SSH 使用无 sudo、无写权限账号。
   - Doris/MySQL 使用只读账号。
   - Redis 使用受限只读 ACL。
   - Flink、Spring API、AI Engine、Prometheus、Grafana、Alertmanager 只通过本机或内网地址访问。
5. 建立 M9 回归与回滚流程：
   - API health。
   - Alertmanager webhook smoke。
   - monitoring deployment-check。
   - 真实只读巡检。
   - 暴露面 checklist。
   - systemd 停止和 Alertmanager receiver 回滚。

## 4. 非目标

- 不把完整开发环境迁移到云端。
- 不让 Web 控制台、Grafana、Prometheus、Alertmanager、Flink Web、Doris FE、MySQL、Redis、Spring API 或 AI Engine 直接暴露公网。
- 不实现生产写操作、任意 Shell、任意 SQL、任意 HTTP 探测、自动重启、自动补数、自动改配置或自动 Savepoint 恢复。
- 不把真实 secret、生产 `.env`、数据库密码、SSH key、Webhook token、Grafana admin 密码或连接串提交到 Git。
- 不把历史 smoke 结果包装为当前事实；M9 验收必须来自当次只读检查。
- 不在 M9 首轮迁移到 PostgreSQL、Loki、独立 ops 节点、SSO 或完整 RBAC。

## 5. 方案选择

### 5.1 备选方案

| 方案 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| `data1` 本机部署 DataSentry API | 与现有监控栈同机，Alertmanager 可走 `127.0.0.1`，最快闭合真实告警入口 | `data1` 故障时 Agent 与监控入口同受影响 | M9 首轮采用 |
| 受控反向通道 | 云端少部署服务，公网暴露更少 | 隧道稳定性、重连和凭据管理复杂，告警入口依赖本机在线 | 保留为备选 |
| 独立 ops 节点 | 最接近长期推荐架构，隔离业务节点和控制面 | 当前成本、迁移和凭据管理工作量较大 | 后续生产增强阶段评估 |

### 5.2 已选方案

M9 首轮采用 `data1` 本机部署：

```text
Prometheus
→ Alertmanager
→ http://127.0.0.1:18000/api/alertmanager/webhook
→ DataSentry API
→ 白名单只读工具
→ SQLite Incident / RCA / Evidence
```

DataSentry API 只监听云端 loopback 地址。用户或本地前端需要访问时，通过 SSH tunnel 映射到本机。云端安全组不需要为 DataSentry API 新增公网入口。

## 6. 部署形态

### 6.1 目录建议

`data1` 上建议使用以下目录：

```text
/opt/datasentry-agent/          # 受控源码或发布目录
/var/lib/datasentry/            # SQLite、运行状态和本地证据
/var/log/datasentry/            # systemd 之外的应用日志，如后续启用文件日志
/etc/datasentry/datasentry.env  # root-only 或服务用户可读的环境文件
/etc/datasentry/targets.toml    # ignored 生产目标配置
```

这些路径是运维约定，不要求提交真实配置内容。仓库内只保存无 secret 示例和操作手册。

### 6.2 systemd 服务

M9 应提供无 secret 的 `systemd` 示例，约束：

- `User=datasentry`。
- `Group=datasentry`。
- `WorkingDirectory=/opt/datasentry-agent`。
- `EnvironmentFile=/etc/datasentry/datasentry.env`。
- `ExecStart` 使用项目虚拟环境中的 `uvicorn datasentry.api:create_app --factory --host 127.0.0.1 --port 18000`。
- `Restart=on-failure`。
- 设置合理 `RestartSec`、`TimeoutStopSec`、资源限制和只读保护选项。

示例文件不得包含真实密码、token 或生产连接串。

### 6.3 环境变量

生产环境文件至少包含：

```bash
DATASENTRY_ENVIRONMENT=production
DATASENTRY_API_HOST=127.0.0.1
DATASENTRY_API_PORT=18000
DATASENTRY_DATABASE_PATH=/var/lib/datasentry/datasentry.db
DATASENTRY_TARGETS_FILE=/etc/datasentry/targets.toml
DATASENTRY_LLM_PROVIDER=mock
```

Doris、MySQL、Redis、LLM 等 secret 仍使用环境变量注入，但只写入云端受限权限文件，不写入仓库示例。M9 首轮允许继续使用 `mock` LLM，以避免生产告警闭环依赖外部模型和 API key。

## 7. Alertmanager 回调

Alertmanager 的 DataSentry receiver 在 M9 中改为：

```yaml
webhook_configs:
  - url: http://127.0.0.1:18000/api/alertmanager/webhook
```

配置原则：

- 只从 Alertmanager 所在主机访问 loopback DataSentry API。
- 保留企业微信或其他通知 receiver 的既有路由，DataSentry 不替代 Alertmanager 的基础通知能力。
- Alertmanager 配置变更必须先备份，变更后执行 reload 或重启前由用户确认。
- 如果 DataSentry API 不可用，Alertmanager 基础通知链路仍应继续工作。

## 8. 暴露面收口

M9 将暴露面收口做成 checklist 和复验步骤，不自动修改云安全组或生产网络配置。

首轮必须确认：

- Prometheus、Grafana、Alertmanager 只绑定 `127.0.0.1` 或内网地址。
- DataSentry API 只绑定 `127.0.0.1`。
- Flink Web、Doris FE、MySQL、Redis、Spring API 和 AI Engine 不直接暴露公网。
- Grafana 访问继续通过 SSH tunnel。
- SSH 生产巡检账号为无 sudo、无写权限账号。
- root 仅用于受控维护窗口、部署和 secret 文件初始化，不作为长期巡检账号。
- Doris root 改密属于单独维护窗口，不和 M9 API 部署混在一个不可回滚步骤中。

## 9. 验证流程

### 9.1 仓库内验证

M9 实施前后至少运行：

```bash
ruff format --check .
ruff check .
mypy src
pytest tests -q -W error::ResourceWarning --cov=datasentry --cov-report=term-missing
```

如果只改文档和部署示例，可使用 `git diff --check` 与 secret 扫描作为最小验证，但进入代码或配置解析实现后必须运行对应 Python 测试。

### 9.2 云端只读验证

云端部署后按顺序执行：

1. `systemctl status datasentry-api`，只读取状态，不打印 secret。
2. `GET http://127.0.0.1:18000/api/health`。
3. `datasentry ops preflight --targets-file /etc/datasentry/targets.toml`。
4. `datasentry monitoring deployment-check --config-file ...`。
5. `datasentry monitoring alert-smoke --config-file ... --payload-file ...`。
6. 真实 K 线只读巡检。
7. AI Engine、MySQL、Redis 的固定只读确认。
8. 暴露面 checklist。

所有输出只记录状态、Incident id、Inspection id、检查名称和脱敏摘要。真实 secret 不得打印、落盘到仓库或写入状态文档。

## 10. 回滚策略

M9 回滚应保持简单：

1. 停止并禁用 `datasentry-api` systemd service。
2. 将 Alertmanager DataSentry receiver 恢复到变更前备份，或临时禁用 DataSentry receiver。
3. reload 或重启 Alertmanager。
4. 复跑 Alertmanager readiness 和基础通知链路检查。
5. 保留 `/var/lib/datasentry/datasentry.db` 作为事故证据，除非用户明确要求清理。

M9 回滚不应删除生产数据、不应改动 StreamLake 作业、不应轮换业务密码。

## 11. 风险与缓解

| 风险 | 缓解 |
|---|---|
| `data1` 故障导致 DataSentry API 不可用 | 保留 Alertmanager 基础通知链路；长期评估独立 ops 节点 |
| API 绑定公网地址 | systemd/env 示例固定 `127.0.0.1`；验收检查监听地址 |
| secret 泄露 | 使用受限权限环境文件；命令输出和状态文档只记录配置状态 |
| SQLite 文件权限错误 | 部署手册要求服务用户拥有 `/var/lib/datasentry` 写权限；health 和 smoke 覆盖 |
| Alertmanager 回调失败 | M9 smoke 覆盖 webhook、Incident detail、timeline、RCA 和 export |
| root 账号继续作为日常巡检入口 | M9 checklist 要求切换到专用只读用户；root 仅用于维护窗口 |
| 暴露面收口误伤业务 | M9 只做检查和人工确认，不自动改安全组或网络配置 |

## 12. 验收标准

M9 仓库资产完成时应满足：

- 仓库包含 M9 设计、实施计划、部署示例和运维手册。
- `systemd`、env、部署手册和暴露面 checklist 均不包含真实 secret。
- 部署手册明确 env 文件和 monitoring 配置不得覆盖已有生产文件。
- 本地部署资产测试、格式、lint、mypy 和全量 pytest 通过。
- `docs/PROJECT_STATUS.md` 记录 M9 本地仓库资产状态、验证结果、剩余风险和 Git 同步状态。

M9 云端部署验证完成时应进一步满足：

- DataSentry API 可在 `data1` 以 systemd 管理方式运行，并只监听 `127.0.0.1`。
- Alertmanager 可通过本机回调自动触发 DataSentry Incident/RCA 闭环。
- M8 的 `deployment-check` 和 `alert-smoke` 在 M9 形态下可复跑。
- 真实只读巡检仍可通过受限工具执行，且不需要把 secret 写入仓库。
- 公网暴露面 checklist 已执行并记录结果。
