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

## 部署前手工检查和目录准备

以下命令只作为人工执行示例，本仓库任务不会 SSH 到 `data1`，不会修改云资源，也不会写入真实 secret。任何云端写操作、账号创建、目录创建、权限变更、systemd 安装或 Alertmanager 配置变更，执行前都必须由用户再次确认。

先确认服务账号存在；若不存在，再在维护窗口按需创建系统组和系统用户：

```bash
getent group datasentry
id datasentry
sudo groupadd --system datasentry
sudo useradd --system --gid datasentry --home-dir /var/lib/datasentry --shell /usr/sbin/nologin datasentry
```

准备配置、数据和日志目录。`/etc/datasentry` 由 root 管理，服务用户只按文件权限读取配置；SQLite 和日志目录必须允许 `datasentry` 写入：

```bash
sudo install -d -o root -g datasentry -m 0750 /etc/datasentry
sudo install -d -o datasentry -g datasentry -m 0750 /var/lib/datasentry
sudo install -d -o datasentry -g datasentry -m 0750 /var/log/datasentry
sudo chown root:datasentry /etc/datasentry
sudo chown datasentry:datasentry /var/lib/datasentry /var/log/datasentry
sudo chmod 0750 /etc/datasentry /var/lib/datasentry /var/log/datasentry
```

确认应用目录来自预期 Git 版本，并且虚拟环境入口存在。不要从未确认来源的工作区启动生产服务：

```bash
cd /opt/datasentry-agent
git status --short --branch
git rev-parse --short HEAD
test -x .venv/bin/uvicorn
```

确认云端配置文件存在并由预期权限保护。`targets.toml` 只能保存目标、白名单和变量名引用，不应包含密码、token、Cookie、私钥或连接串等 secret 值：

```bash
test -f /etc/datasentry/targets.toml
test -f /etc/datasentry/datasentry.env
sudo chown root:datasentry /etc/datasentry/targets.toml /etc/datasentry/datasentry.env
sudo chmod 0640 /etc/datasentry/targets.toml /etc/datasentry/datasentry.env
```

最后确认服务用户能读取配置，并能写入 SQLite 和日志目录。示例中的临时文件只用于权限验证，完成后按维护窗口流程清理；不要把真实 secret 打印到终端、日志或工单中：

```bash
sudo -u datasentry test -r /etc/datasentry/targets.toml
sudo -u datasentry test -r /etc/datasentry/datasentry.env
sudo -u datasentry test -w /var/lib/datasentry
sudo -u datasentry test -w /var/log/datasentry
sudo -u datasentry sh -c 'touch /var/lib/datasentry/.write-check /var/log/datasentry/.write-check'
```

## systemd 安装

以下命令展示步骤，不包含真实 secret。执行云端写操作前必须由用户再次确认。service 文件可在审核后覆盖安装；env 文件包含生产 secret，必须按特殊规则处理，不能在重跑部署时覆盖。

```bash
sudo install -o root -g root -m 0644 deploy/systemd/datasentry-api.service.example /etc/systemd/system/datasentry-api.service
```

仅当 `/etc/datasentry/datasentry.env` 不存在、且这是首次初始化时，才从示例文件引导创建 env 文件。下面的模式会先检查目标文件不存在；如果文件已经存在，命令会停止，不会复制示例覆盖真实生产配置：

```bash
test ! -e /etc/datasentry/datasentry.env
sudo cp -n config/datasentry.env.example /etc/datasentry/datasentry.env
sudo chown root:datasentry /etc/datasentry/datasentry.env
sudo chmod 0640 /etc/datasentry/datasentry.env
```

如果 `/etc/datasentry/datasentry.env` 已存在，不要把 `config/datasentry.env.example` 复制到该路径。只允许人工对比示例文件和现有生产文件，补齐必要的非 secret 配置键，并保留现有真实 secret。编辑 `/etc/datasentry/datasentry.env` 时只在云端受限文件中加入真实 secret，不要把真实值复制回仓库。

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
