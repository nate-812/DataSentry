# M8 监控部署闭环运维手册

本文档说明如何在 Prometheus、Grafana、Alertmanager 已由人工或现有运维流程部署后，使用 DataSentry 做只读部署验收和告警诊断闭环 smoke。

## 安全边界

M8 允许：

- 固定读取 Prometheus readiness 和规则 API。
- 固定读取 Alertmanager readiness 和 status API。
- 固定读取 Grafana health API。
- 向 DataSentry API 发送脱敏 Alertmanager fixture，创建本地 Incident/RCA 证据。

M8 不允许：

- 自动安装、启动、重启或重载 Prometheus/Grafana/Alertmanager。
- 写入 Alertmanager silence、Grafana dashboard 或 Prometheus 配置。
- 保存 Grafana token、企业微信机器人 key、Webhook secret、数据库密码或真实 `.env`。
- 把历史验收结果包装成当前事实。

## 配置

复制无 secret 示例：

```bash
cp config/monitoring.example.toml config/monitoring.toml
```

`config/monitoring.toml` 应只包含 base URL 和期望告警名，不包含 username、password、token、query 或 fragment。

## 部署验收

运行只读部署检查：

```bash
datasentry monitoring deployment-check \
  --config-file config/monitoring.toml
```

输出 JSON 中 `status` 为：

- `passed`：Prometheus、Alertmanager、Grafana 的必需检查均通过。
- `failed`：至少一个检查失败，查看 `checks[].summary` 和 `checks[].details`。

重点检查项：

- `prometheus_ready`
- `prometheus_rules_loaded`
- `alertmanager_ready`
- `alertmanager_datasentry_route`
- `grafana_health`

建议保存证据：

```bash
datasentry monitoring deployment-check \
  --config-file config/monitoring.toml \
  > var/m8-monitoring-deployment-check.json
```

不要把真实环境输出中可能包含内部地址的证据文件提交到 Git。

## 告警闭环 Smoke

先启动 DataSentry API，并确保它使用本轮 smoke 的 SQLite 数据库和目标配置：

```bash
DATASENTRY_DATABASE_PATH=var/datasentry-m8.db \
DATASENTRY_TARGETS_FILE=config/targets.toml \
DATASENTRY_LLM_PROVIDER=mock \
  uvicorn datasentry.api:create_app --factory --host 127.0.0.1 --port 8000
```

运行 Alertmanager → DataSentry smoke：

```bash
datasentry monitoring alert-smoke \
  --config-file config/monitoring.toml \
  --payload-file tests/fixtures/alertmanager/kline_freshness_firing.json
```

该命令会调用：

- `POST /api/alertmanager/webhook`
- `GET /api/incidents/{incident_id}`
- `GET /api/incidents/{incident_id}/timeline`
- `POST /api/incidents/{incident_id}/rca`
- `GET /api/incidents/{incident_id}/export`

建议保存证据：

```bash
datasentry monitoring alert-smoke \
  --config-file config/monitoring.toml \
  --payload-file tests/fixtures/alertmanager/kline_freshness_firing.json \
  > var/m8-alert-smoke.json
```

## 结果记录

完成一次现场 M8 验收后，记录：

- deployment-check 的整体状态和失败项。
- alert-smoke 的 Incident id。
- RCA/export 是否生成。
- 本次 DataSentry API 使用的数据库路径。
- 是否使用真实监控栈地址，还是本地测试地址。

不要记录真实 secret 值。
