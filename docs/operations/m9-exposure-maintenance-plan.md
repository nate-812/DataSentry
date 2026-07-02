# M9 暴露面维护预案

本文档用于云端实例暂不开启时的本地准备，以及下次 `data1` 维护窗口的执行顺序。它不替代人工审批，不自动修改云安全组、主机防火墙、systemd、数据库账号或业务配置。

## 使用场景

- 当前不开云端实例，只在本地仓库准备下一次维护窗口需要的步骤、验证和证据模板。
- 下次用户明确打开 `data1` 后，按本文档逐项确认公网暴露面、账号权限、secret 管理和回归证据。
- 本文档只描述人工 runbook。不开云端实例时，不执行 SSH，不访问生产端口，不修改云安全组，不打印真实 secret，不开放生产写 Runbook。

## 本地准备

本地可先完成以下事项：

1. 确认当前仓库状态干净：

   ```bash
   git status --short --branch
   git diff --check
   ```

2. 确认维护窗口使用的文档入口存在：

   ```bash
   test -f docs/operations/m9-production-deployment.md
   test -f docs/operations/production-exposure-checklist.md
   test -f docs/operations/m9-exposure-maintenance-plan.md
   ```

3. 确认部署资产仍保持 loopback 和无 secret 边界：

   ```bash
   .venv/bin/pytest tests/unit/test_deployment_assets.py -q
   ```

4. 维护窗口前准备一份空白证据记录，记录命令、时间、操作者、状态和失败项。不要提前填写历史 smoke 结果作为当前事实。

## 维护窗口顺序

下次 `data1` 打开后，先做只读确认，再决定是否执行任何写操作。

1. 确认 DataSentry 自启动状态：

   ```bash
   systemctl is-enabled datasentry-api
   systemctl is-active datasentry-api
   systemctl is-enabled datasentry-alertmanager-proxy.socket
   systemctl is-active datasentry-alertmanager-proxy.socket
   ```

   如果本轮不需要 DataSentry API 自启动，必须经用户确认后再执行 `disable`。不要在未确认服务用途前停止或禁用。

2. 确认 DataSentry API 和 Docker bridge proxy 仍只监听受控地址：

   ```bash
   curl -fsS http://127.0.0.1:18000/api/health
   curl -fsS http://172.17.0.1:18000/api/health
   ```

3. 只读复查当前监听与云安全组事实，记录发现，不立即修改：

   - DataSentry API 是否只在 `127.0.0.1:18000`。
   - Docker bridge proxy 是否只在 `172.17.0.1:18000`。
   - Prometheus、Grafana、Alertmanager 是否仅在 loopback 或内网地址。
   - Flink Web、Doris FE、MySQL、Redis、Spring API、AI Engine 是否仍存在公网监听或公网安全组入口。

4. 按组件逐项收口。每次只处理一个组件，先记录当前状态，再执行变更，再运行对应只读验证。若验证失败，立刻按本组件回滚方案恢复，不继续处理下一项。

5. 全部组件处理后运行 M9 回归：

   ```bash
   datasentry ops preflight --targets-file /etc/datasentry/targets.toml
   datasentry monitoring deployment-check --config-file /etc/datasentry/monitoring.toml
   datasentry monitoring alert-smoke --config-file /etc/datasentry/monitoring.toml --payload-file tests/fixtures/alertmanager/kline_freshness_firing.json
   datasentry inspection run --question "为什么K线不更新" --targets-file /etc/datasentry/targets.toml --knowledge-root knowledge --database-path /var/lib/datasentry/datasentry.db
   ```

## 组件收口清单

| 组件 | 目标状态 | 变更前只读确认 | 变更后验证 | 回滚提示 |
|---|---|---|---|---|
| Flink Web | 不直接暴露公网，仅保留内网或 SSH tunnel 访问 | 记录监听地址、访问来源和当前 Job 状态 | 确认 Flink REST 可从受控路径访问，三条 Job 仍为 RUNNING | 恢复上一版网络或安全组规则，再复查 Job 状态 |
| Doris FE | 不直接暴露公网；Doris root 改密放入单独维护窗口 | 记录 FE 监听、账号清单和 DataSentry 只读账号状态 | 固定 freshness 查询成功，Spring/Flink 使用账号不受影响 | 恢复上一版网络规则；账号变更按独立回滚方案处理 |
| MySQL | 不直接暴露公网，只允许受控来源和只读诊断账号 | 记录监听、安全组、`risk_control` 表状态和只读账号权限 | 固定 `risk_rules`、`whale_thresholds` 只读样本查询成功 | 恢复上一版网络规则，不回滚已确认的安全密码轮换 |
| Redis | 不直接暴露公网，只允许计划内只读 ACL 命令，禁止 `KEYS` | 记录监听、安全组、ACL 用户和禁用命令状态 | 固定 dbsize 与 `risk:blacklist:*` 样本只读探测成功 | 恢复上一版网络规则；ACL 改动按单独审批回滚 |
| Spring API | 不直接暴露公网，通过内网、反向代理或 SSH tunnel 访问 | 记录监听、健康检查和 K 线固定读接口状态 | `/api/kline/{symbol}?interval=1min&limit=...` 固定读探针成功 | 恢复上一版入口规则，并确认 API health |
| AI Engine | 不直接暴露公网，明确 systemd 或进程管理方式 | 记录 8000 监听、`/health`、当前进程来源和 systemd 状态 | `/health` 返回 ok，DataSentry 固定 HTTP GET 成功 | 恢复上一版进程或入口规则，并记录启动方式 |

Doris root 改密、云安全组大范围重构、生产写 Runbook 开放和自动化执行都必须单独维护窗口处理，不能混入本轮暴露面收口。

## 回滚边界

- 网络或监听收口失败时，只回滚本组件最近一次网络入口变更。
- 不删除生产数据，不重置 SQLite 证据库，不清空 Kafka、Doris、MySQL 或 Redis 数据。
- 不在回滚中引入任意 Shell、任意 SQL、自动补数、自动重启或自动 Savepoint 恢复。
- 若 Alertmanager 回调异常，先恢复 receiver 备份，再复查 readiness 和 DataSentry webhook 200。
- 若 `datasentry-api` 或 `datasentry-alertmanager-proxy.socket` 不需要自启动，必须用户确认后再 `disable`；若需要保留，则只记录状态，不变更。

## 证据记录模板

```text
维护窗口：
操作者：
云端实例：
Git commit：

变更项：
变更前状态：
用户确认：
执行动作：
变更后验证：
失败项：
回滚动作：
Incident id：
Inspection id：
未验证项：
secret 处理确认：未打印、未落盘到仓库、未写入日志或 RCA
```

证据只记录状态、ID、脱敏摘要和失败项。真实 secret、Cookie、私钥、完整连接串、业务敏感样本值不得进入证据记录。

## 本地验证

不开云端实例时，至少运行：

```bash
.venv/bin/pytest tests/unit/test_deployment_assets.py -q
.venv/bin/ruff format --check .
.venv/bin/ruff check .
.venv/bin/mypy src
```

如果只是修改运维文档，`tests/unit/test_deployment_assets.py` 是最小相关测试；提交前仍需说明是否运行了更大范围验证。
