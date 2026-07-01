# M8 监控部署闭环设计

## 1. 文档状态

- 项目：DataSentry
- 阶段：M8 监控部署闭环
- 日期：2026-07-01
- 状态：本轮实施输入
- 主题：Prometheus/Grafana/Alertmanager 真实部署验收 + DataSentry 告警诊断闭环

## 2. 背景

M3 已交付 Prometheus、Grafana、Alertmanager 模板和本地通知模拟；M5 已补齐 Alertmanager → DataSentry API 的 Incident、timeline、RCA 和 Markdown export 闭环；M7.2 已补齐 live smoke 前的目标配置和 secret 预检。当前缺口是：监控栈真实部署后没有一个仓库内、可复跑、可保存证据的验收入口。

M8 不把 DataSentry 变成 Prometheus/Grafana/Alertmanager 的部署器。部署仍由人工或现有运维流程完成。DataSentry 只做只读验收和告警闭环 smoke，确认“监控栈已加载 DataSentry 需要的规则和路由，并且一条真实 Webhook 能驱动 Incident/RCA 链路”。

## 3. 目标

1. 提供无 secret 的监控栈目标配置示例，描述 Prometheus、Grafana、Alertmanager 和 DataSentry API 的 base URL。
2. 提供 `datasentry monitoring deployment-check`，只读检查监控栈部署状态：
   - Prometheus readiness。
   - Prometheus 已加载关键 StreamLake 告警规则。
   - Alertmanager readiness。
   - Alertmanager 配置中存在 DataSentry Webhook 路由。
   - Grafana health。
3. 提供 `datasentry monitoring alert-smoke`，向 DataSentry API 发送脱敏 Alertmanager fixture，并验证：
   - Webhook 返回 accepted 和 incident id。
   - Incident detail 可读取。
   - Timeline 可读取且包含告警事件。
   - RCA 可生成。
   - Markdown export 可读取。
4. 修正仓库 Alertmanager 示例中的 DataSentry Webhook URL，使其匹配当前 FastAPI 路由 `/api/alertmanager/webhook`。
5. 增加运维手册，固化 M8 真实部署验收步骤、证据保存方式和安全边界。

## 4. 非目标

- 不自动安装、启动、重启或重载 Prometheus/Grafana/Alertmanager。
- 不保存 Grafana token、企业微信机器人 key、Alertmanager secret、生产连接串或真实 `.env`。
- 不通过 Grafana 写 API 导入 dashboard。
- 不通过 Alertmanager silence、ack、receiver API 做写操作。
- 不绕过 M2 白名单工具做任意 Shell 或任意 HTTP 探测。
- 不把历史验收结果包装为当前事实；每次结论必须来自当次只读检查。

## 5. 配置与安全边界

新增 `config/monitoring.example.toml`，只包含无凭据 URL：

```toml
[endpoints]
prometheus_base_url = "http://prometheus.example:9090"
grafana_base_url = "http://grafana.example:3000"
alertmanager_base_url = "http://alertmanager.example:9093"
datasentry_api_base_url = "http://datasentry.example:8000"

expected_alerts = [
  "FlinkJobNotRunning",
  "KafkaConsumerLagHigh",
  "KlineFreshnessStale",
]
```

URL 不允许包含 username/password、query 或 fragment。CLI 输出只包含检查状态、HTTP status code、缺失告警名和中文说明，不输出 header、token 或响应全文。

## 6. 部署验收设计

新增 `datasentry.monitoring.deployment`：

- `MonitoringDeploymentConfig`：加载和校验监控端点配置。
- `MonitoringCheckResult`：记录单项检查名称、状态、摘要和安全 details。
- `MonitoringDeploymentReport`：汇总所有检查，整体状态为 `passed` 或 `failed`。
- `run_monitoring_deployment_check`：通过注入的 HTTP client 执行只读 GET。

检查规则：

1. `prometheus_ready`：GET `/-/ready` 返回 2xx。
2. `prometheus_rules_loaded`：GET `/api/v1/rules` 返回 `status=success`，并能在 alerting rules 中找到 `expected_alerts`。
3. `alertmanager_ready`：GET `/-/ready` 返回 2xx。
4. `alertmanager_datasentry_route`：GET `/api/v2/status`，从 `config.original` 中确认包含 `/api/alertmanager/webhook`。
5. `grafana_health`：GET `/api/health` 返回 2xx。

任何必需检查失败，整体状态为 `failed`。网络异常归一为安全失败摘要，不暴露异常中的敏感 URL 查询参数。

## 7. Alert Smoke 设计

新增 `datasentry.monitoring.smoke`：

- `AlertSmokeReport`：记录闭环状态、Incident id、诊断问题和每一步检查结果。
- `run_alertmanager_smoke`：通过注入 HTTP client 调用 DataSentry API。

流程：

```text
读取本地 Alertmanager fixture
→ POST /api/alertmanager/webhook
→ GET /api/incidents/{incident_id}
→ GET /api/incidents/{incident_id}/timeline
→ POST /api/incidents/{incident_id}/rca
→ GET /api/incidents/{incident_id}/export
→ 输出 JSON smoke report
```

该 smoke 只写 DataSentry 本地 SQLite，因为它的目的就是验证告警进入 DataSentry 后的事件闭环；它不写 StreamLake 生产系统，也不写 Alertmanager/Grafana/Prometheus。

## 8. CLI 形态

新增 Typer 命令组 `monitoring`：

```bash
datasentry monitoring deployment-check --config-file config/monitoring.toml
datasentry monitoring alert-smoke --config-file config/monitoring.toml --payload-file tests/fixtures/alertmanager/kline_freshness_firing.json
```

两个命令均输出 JSON；失败时命令仍输出结构化报告，并用退出码 `2` 表示验收不通过。配置解析错误沿用 `DataSentryError` 安全 JSON。

## 9. 测试与验证

最小验证集：

1. 单元测试覆盖监控配置 URL 安全校验。
2. 单元测试覆盖 Prometheus 规则加载成功和缺失告警失败。
3. 单元测试覆盖 Alertmanager route 配置成功和缺失失败。
4. 单元测试覆盖 Alert smoke 的完整闭环与失败归一。
5. CLI 场景测试覆盖两个新命令的 JSON 输出和退出码。
6. 监控模板测试确认 Alertmanager 示例 URL 指向 `/api/alertmanager/webhook`。
7. 运行 Ruff、mypy、pytest，必要时运行前端 typecheck/build 以确认未影响 Web。

## 10. 验收标准

M8 完成时应满足：

- 仓库有 M8 设计、计划和运维手册。
- 监控目标配置示例不含真实 secret。
- `datasentry monitoring deployment-check` 可对真实监控栈执行只读部署验收。
- `datasentry monitoring alert-smoke` 可复跑 DataSentry 告警诊断闭环。
- Alertmanager 示例路由与当前 FastAPI 路由一致。
- 项目状态文档记录 M8 已实现和尚未执行现场真实部署验收的事实边界。
