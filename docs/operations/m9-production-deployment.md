# M9 生产化部署运维手册

本文档说明如何把 DataSentry API 作为 `data1` 本机 loopback 服务运行，并让 Alertmanager 通过本机地址回调。开发、提交和版本管理仍以本地仓库和 GitHub 为准；云端只运行明确 Git 版本。

## 安全边界

允许：

- 以独立系统用户运行 DataSentry API。
- 让 API 只监听 `127.0.0.1:18000`。
- 让 Alertmanager 调用 `http://127.0.0.1:18000/api/alertmanager/webhook`。
- 使用固定只读工具执行巡检。
- 在 DataSentry SQLite 中保存 Incident、timeline、RCA 和 evidence。

不允许：

- 直接暴露 DataSentry API、Grafana、Prometheus、Alertmanager、Flink Web、Doris FE、MySQL、Redis、Spring API 或 AI Engine 到公网。
- 写入生产数据库、执行任意 Shell、自动重启、自动补数、自动改配置或自动 Savepoint 恢复。
- 把真实 secret 写入 Git、README、Issue、PR、SQLite、RCA、日志或命令输出。

## 云端目录

建议在 `data1` 使用：

```text
/opt/datasentry-agent/
/var/lib/datasentry/
/var/log/datasentry/
/etc/datasentry/datasentry.env
/etc/datasentry/targets.toml
```

`/etc/datasentry/datasentry.env` 和 `/etc/datasentry/targets.toml` 是云端真实配置，不提交到 Git。

## 仓库产物

```bash
deploy/systemd/datasentry-api.service.example
config/datasentry.env.example
docs/operations/production-exposure-checklist.md
```

## 部署前确认

```bash
git status --short --branch
git rev-parse --short HEAD
git diff --check
```

记录将部署的 Git commit。不要部署未提交或来源不明的工作区。

## systemd 安装

以下命令展示步骤，不包含真实 secret。执行云端写操作前必须由用户再次确认。

```bash
sudo install -o root -g root -m 0644 deploy/systemd/datasentry-api.service.example /etc/systemd/system/datasentry-api.service
sudo install -o root -g datasentry -m 0640 config/datasentry.env.example /etc/datasentry/datasentry.env
```

编辑 `/etc/datasentry/datasentry.env` 时只在云端受限文件中加入真实 secret。不要把真实值复制回仓库。

## 启动和健康检查

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now datasentry-api
systemctl status datasentry-api
curl -fsS http://127.0.0.1:18000/api/health
```

`systemctl status` 和 `curl` 输出只能记录服务状态、HTTP 状态和脱敏摘要。

## Alertmanager 回调

将 DataSentry receiver 指向：

```yaml
webhook_configs:
  - url: http://127.0.0.1:18000/api/alertmanager/webhook
```

变更前备份 Alertmanager 配置。变更后先检查 readiness，再做 smoke。

## M9 回归

```bash
datasentry ops preflight --targets-file /etc/datasentry/targets.toml
datasentry monitoring deployment-check --config-file /etc/datasentry/monitoring.toml
datasentry monitoring alert-smoke --config-file /etc/datasentry/monitoring.toml --payload-file tests/fixtures/alertmanager/kline_freshness_firing.json
datasentry inspection run --question "为什么K线不更新" --targets-file /etc/datasentry/targets.toml --knowledge-root knowledge --database-path /var/lib/datasentry/datasentry.db
```

记录 Incident id、Inspection id、整体状态和失败项，不记录真实 secret。

## 本地访问

本地查看 API 或控制台时继续使用 SSH tunnel：

```bash
ssh -L 18000:127.0.0.1:18000 data1
```

Grafana、Prometheus 和 Alertmanager 继续通过各自 tunnel 访问，不开放公网。

## 回滚

```bash
sudo systemctl stop datasentry-api
sudo systemctl disable datasentry-api
```

然后将 Alertmanager receiver 恢复到变更前备份，reload 或重启 Alertmanager，并复查 readiness。保留 `/var/lib/datasentry/datasentry.db` 作为证据，除非用户明确要求清理。
