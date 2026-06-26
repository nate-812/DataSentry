# M3 监控看板与通知设计

## 1. 文档状态

- 项目：DataSentry
- 阶段：M3 监控看板与通知
- 日期：2026-06-26
- 状态：已批准，作为 M3 实施计划输入
- 范围选择：仓库内配置与集成代码优先，不直接上服务器部署

## 2. 背景

M2 已完成真实只读工具、工具审计、目标配置、脱敏和端到端只读影子巡检。M3 的目标是在不扩大生产权限的前提下，为 StreamLake 建立可提交、可测试、可后续部署的监控与通知基线。

本阶段不重写 Prometheus、Grafana 或 Alertmanager。DataSentry 只补充 StreamLake 领域上下文：将关键告警映射为只读诊断问题，复用 M2 稳定边界执行诊断，并生成包含证据、未知项和建议的消息。

## 3. 目标

M3 交付一个仓库内可验证的可观测性套件：

1. 提供 Prometheus scrape 和告警规则模板，覆盖主机、Kafka、Flink、Doris、业务数据新鲜度、API 健康和 DataSentry 自监控。
2. 提供 Alertmanager 路由模板，默认将关键告警发送到 DataSentry Webhook 占位，并保留企业微信机器人与通用 Webhook receiver 模板。
3. 提供 Grafana provisioning 和 dashboard JSON，覆盖 StreamLake 总览、主机、Kafka、Flink、Doris 与新鲜度、DataSentry 自监控骨架。
4. 在 `datasentry.notifications` 中实现 Alertmanager payload 解析、告警去重 key、诊断问题映射和企业微信 Markdown / 通用 JSON 消息格式化。
5. 在 `datasentry.observability` 中定义 DataSentry 自身 Prometheus 指标名称和文本导出格式，供 M4 API 和后续 Worker 复用。
6. 提供本地 CLI 模拟命令，用脱敏 fixture 输入 Alertmanager payload，输出将发送的企业微信或通用 Webhook 消息。

## 4. 非目标

M3 不做以下事项：

- 不真实部署 Prometheus、Grafana、Alertmanager 或 Exporter。
- 不接触、读取或提交真实企业微信机器人 URL、token 或其他通知 secret。
- 不引入 FastAPI、后台 Worker、Web 控制台或 SSE / WebSocket。
- 不实现 Loki、Alloy 或集中日志采集。
- 不实现 Incident 生命周期、告警自动合并入库或关闭逻辑。
- 不绕过 M2 白名单工具网关直接访问 SSH、数据库、Redis、Kafka、Flink 或生产 HTTP 接口。

## 5. 方案选择

采用“配置与集成代码并进”的方案：

- `monitoring/` 保存可部署前的 Prometheus、Alertmanager 和 Grafana 模板。
- `datasentry.notifications` 提供告警到诊断消息的纯 Python 内核。
- CLI 使用本地 fixture 验证“告警消息包含实时诊断证据”的产品闭环。

没有采用“只做配置模板”，因为它无法验证告警消息是否包含 DataSentry 的证据化诊断。没有采用“提前做 HTTP Webhook 服务”，因为 FastAPI 和线上监听属于 M4，提前引入会扩大本阶段范围。

## 6. 目录结构

M3 新增或扩展以下结构：

```text
monitoring/
├── prometheus/
│   ├── prometheus.example.yml
│   └── rules/
│       └── streamlake.rules.yml
├── alertmanager/
│   └── alertmanager.example.yml
└── grafana/
    ├── provisioning/
    │   ├── datasources/
    │   │   └── prometheus.yml
    │   └── dashboards/
    │       └── streamlake.yml
    └── dashboards/
        ├── streamlake-overview.json
        ├── streamlake-hosts.json
        ├── streamlake-kafka.json
        ├── streamlake-flink.json
        ├── streamlake-doris-freshness.json
        └── datasentry-self-monitoring.json

src/datasentry/
├── notifications/
│   ├── __init__.py
│   ├── alertmanager.py
│   ├── deduplication.py
│   ├── messages.py
│   └── service.py
└── observability/
    ├── __init__.py
    ├── metrics.py
    └── prometheus.py

tests/
├── fixtures/alertmanager/
└── unit/notifications/
```

## 7. 架构

M3 的逻辑链路是：

```text
Prometheus 告警规则
→ Alertmanager 分组、去重和路由
→ DataSentry Webhook 占位
→ Alertmanager payload 解析
→ 告警标签映射为诊断问题
→ LiveInspectionService 或测试替身
→ 企业微信 Markdown / 通用 JSON 消息
```

在仓库内验证时，CLI 直接读取 fixture，不启动 HTTP 服务。未来 M4 引入 FastAPI 后，只需要把 HTTP handler 的请求体交给 `NotificationService`，不需要重写解析、去重或消息格式化。

## 8. 组件设计

### 8.1 Prometheus 配置

`prometheus.example.yml` 只保存示例 target 和占位域名，例如 `data1:9100`、`data1:8081` 和 `datasentry:8000`。真实环境中的地址和凭据不进入仓库。

`streamlake.rules.yml` 按组件分组：

- `streamlake_host`：主机不可达、磁盘空间不足、inode 使用率过高、时间同步异常。
- `streamlake_kafka`：Kafka Broker 不可达、Topic 无写入推进、Consumer Group lag 异常。
- `streamlake_flink`：关键 Job 缺失或非 RUNNING、Checkpoint 连续失败、反压异常。
- `streamlake_doris`：FE / BE 不可达、业务表新鲜度超时。
- `streamlake_api`：Spring API 或 AI Engine 健康检查失败。
- `datasentry_self`：DataSentry 工具调用失败率、诊断失败率和通知失败数。

规则只依赖指标名称和标签约定，不包含真实 secret。对现场尚未稳定确认的 exporter 指标，使用明确注释标记“部署时需确认指标名”，但不留下未决业务规则。

### 8.2 Grafana 看板

Grafana dashboard 以 JSON 文件保存，先提供可导入骨架和关键 panel：

- StreamLake 总览：组件状态、关键 Job、数据新鲜度、活跃告警入口。
- 主机：CPU、内存、磁盘、inode、网络和时间同步。
- Kafka：Broker 状态、Topic 写入速率、Offset 推进、Consumer Group lag。
- Flink：Job 状态、Checkpoint、TaskManager、Slot、吞吐和反压。
- Doris 与新鲜度：FE / BE 状态、业务表最新事件时间、查询失败提示。
- DataSentry 自监控：工具调用、诊断、通知和内部错误。

Dashboard 文件必须是合法 JSON，并使用固定 uid，避免重复导入时生成不可追踪副本。

### 8.3 Alertmanager 配置

Alertmanager 模板包含：

- 根路由按 `alertname`、`component` 和 `severity` 分组。
- 关键告警路由到 `datasentry-webhook` 占位 URL。
- 企业微信机器人 receiver 使用占位 URL，例如 `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=<WECHAT_WORK_BOT_KEY>`。
- 通用 Webhook receiver 使用占位 URL。
- 抑制关系表达上游故障对下游故障的影响，例如 Kafka Broker 不可用时抑制相关 Topic lag 告警。

真实 URL、机器人 key、认证 token 和消息渠道 secret 必须通过部署环境注入，不能写入仓库。

### 8.4 Notifications 内核

`AlertmanagerPayload` 负责解析 Alertmanager v4 Webhook 常见字段，包括 `status`、`receiver`、`groupLabels`、`commonLabels`、`commonAnnotations` 和 `alerts`。解析失败返回稳定错误码和中文 message。

`AlertDeduplicationKey` 使用以下字段生成稳定 key：

```text
alertname + component + service + job + instance + severity + startsAt
```

key 用于消息摘要和未来 Incident 聚合，不在 M3 中写入数据库。

`AlertQuestionMapper` 将告警映射为诊断问题，例如：

- `FlinkJobNotRunning` → `为什么 Flink 关键 Job 未运行`
- `KlineFreshnessStale` → `为什么 K线数据不更新`
- `KafkaConsumerLagHigh` → `为什么 Kafka 消费延迟升高`
- 未识别告警 → `请巡检 StreamLake 当前状态`

`NotificationService` 只依赖一个可注入的诊断 runner。生产实现使用 M2 的 `LiveInspectionService.run(question)`，测试使用内存替身返回固定 Observation 和 Finding。

### 8.5 消息格式

企业微信 Markdown 消息必须包含：

1. 告警状态、严重级别和组件。
2. DataSentry 当前结论。
3. 已确认关键证据，带来源和观察时间。
4. 未知项或工具失败摘要。
5. 推荐下一步。
6. 去重 key。

通用 Webhook JSON 使用稳定字段：

```json
{
  "status": "firing",
  "severity": "critical",
  "component": "flink",
  "deduplication_key": "...",
  "diagnosis_question": "...",
  "finding_summaries": [],
  "confirmed_evidence": [],
  "unknowns": [],
  "recommended_actions": []
}
```

所有消息格式化必须复用现有脱敏工具，不能输出 token、password、authorization header、cookie 或真实 webhook URL。

### 8.6 Observability 内核

`datasentry.observability` 定义 M3 可用的自监控指标：

- `datasentry_tool_invocations_total`
- `datasentry_tool_failures_total`
- `datasentry_inspections_total`
- `datasentry_inspection_failures_total`
- `datasentry_notification_events_total`
- `datasentry_notification_failures_total`
- `datasentry_notification_format_seconds`

M3 只实现文本导出格式和单元测试，不启动指标 HTTP endpoint。M4 API 接入时可以直接暴露 `/metrics`。

## 9. 错误处理

- Alertmanager payload 无效：返回 `notification.invalid_payload`，CLI 退出码为 2。
- 告警无法映射：使用默认巡检问题，不丢弃告警。
- 诊断 runner 失败：消息仍输出告警基础信息，并将诊断状态标记为 `unknown`。
- 消息格式化失败：返回 `notification.format_failed`，不得吞掉异常。
- 检测到敏感字段：输出脱敏值，并在测试中覆盖常见 secret 形态。

## 10. 测试与验证

M3 的最小验证集：

1. `pytest` 覆盖 notifications、observability 和配置文件解析。
2. `ruff check .` 通过。
3. `mypy src/datasentry` 通过。
4. Prometheus 和 Alertmanager YAML 可解析。
5. Grafana dashboard JSON 可解析，且每个文件包含 uid、title、panels。
6. CLI fixture 模拟输出包含告警摘要、诊断结论、证据和去重 key。
7. 消息脱敏测试确认 secret 不会出现在输出中。

## 11. 安全边界

- M3 不新增生产写操作。
- M3 不读取异常表 `RECOVER_YOUR_DATA_info`。
- M3 不读取真实 `.env`、Shell History、私钥、Cookie、token 或 webhook secret。
- M3 不通过 Prometheus、Grafana 或通知逻辑绕过 M2 白名单工具网关。
- 所有示例配置只能使用占位值。

## 12. 验收标准

M3 完成时应满足：

- 仓库包含完整监控配置模板和 dashboard JSON。
- 本地 fixture 可模拟一条关键 Alertmanager 告警。
- 模拟命令可输出企业微信 Markdown 和通用 Webhook JSON。
- 输出消息包含 DataSentry 诊断证据，而不只是 Prometheus 阈值文本。
- 同一告警组可生成稳定去重 key。
- 全量相关测试、Ruff 和 mypy 通过。

