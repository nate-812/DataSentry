# M2 真实只读工具交接说明

更新时间：2026-06-26

## 0. 当前阶段

M2 已完成全量验证并通过 Pull Request #2 合并到 `main`。HTTP、SSH 主机/服务状态、
Kafka Topic/Offset/Consumer Group、Doris、Redis、MySQL 规则表和 `spring_api` 有限日志已完成首轮现场契约探测；
Kline 端到端只读影子巡检已完成且 9/9 工具成功。MySQL 异常表 `RECOVER_YOUR_DATA_info` 的根因仍需安全复盘。
下个窗口开始 M3 前必须：

1. 回到主仓库 `/Users/nate/Codex/data-sentry-agent`，确认 `main` 已同步到 `origin/main`。
2. 从最新 `main` 创建 M3 功能分支。
3. 新窗口仍需先读取 `docs/PROJECT_STATUS.md`。
4. 不要读取异常表 `RECOVER_YOUR_DATA_info` 内容；该问题作为安全复盘事项单独处理。

M2 worktree 可作为历史现场验证记录保留；不要在未确认用途前删除、重置或覆盖它。

## 0.1 下个会话最短恢复摘要

下个会话不用让用户解释 Git 或本轮进度，直接在主仓库执行：

```bash
cd /Users/nate/Codex/data-sentry-agent
git status --short --branch
git log --oneline -8
git diff --check
```

当前已知状态：

- 当前分支：`main`
- 合并提交：`bf4aa04 feat: 接入 M2 真实只读工具`
- GitHub 同步状态：M2 PR #2 已合并；主仓库 `main` 已拉取合并结果，本文档收尾提交用于记录 M3 起点。
- M2 功能分支：`feat/m2-real-readonly-tools` 保留为历史分支，工作区位于 `.worktrees/feat-m2-real-readonly-tools`。
- 本文件更新后应产生新的文档收尾提交；下个会话以 `git log -1 --oneline` 为准。
- 最近检查点：
  - `729cec8 docs: 完成M2收尾交接`
  - `74b838a docs: 更新M2远端同步状态`
  - `916b6fe docs: 更新M2会话交接状态`
  - `1edb57e docs: 更新M2数据库与日志探测状态`
  - `437e607 fix: 归一数据库认证失败错误`
  - `fa012ad fix: 归一Redis只读超时错误`
  - `ee6222e fix: 正确归类缺失秘密配置`
  - `a8be87f docs: 更新M2云端探测交接`
  - `5238f47 fix: 支持配置Kafka bootstrap`
  - `aced0de fix: 兼容SSH主机状态契约`
- 当前本地工作树在本次交接提交后应保持干净；`config/targets.toml`、`var/`、缓存目录为 ignored。
- 下一步从最新 `main` 创建 M3 分支，开始监控看板与通知。
- Kafka Consumer Group `flink-kline-group` 已恢复，固定 group 工具复测为 `VISIBLE` 并可读取 lag。
- ignored `config/targets.toml` 当前现场探测值：
  - Doris：`data1:9030`，database `streamlake`，username `root`，无密码。
  - MySQL：`data1:3306`，database `risk_control`，username `root`，password env `DATASENTRY_MYSQL_PASSWORD`。
  - Redis：`data1:6379`，DB `0`，username `default`，password env `DATASENTRY_REDIS_PASSWORD`。
- `spring_api` 日志：file `/opt/StreamLake-Binance/api-server/api.log`。
- PR：<https://github.com/nate-812/DataSentry/pull/2>，已合并。

## 1. 当前工作位置

- 主仓库：`/Users/nate/Codex/data-sentry-agent`
- M2 worktree：`/Users/nate/Codex/data-sentry-agent/.worktrees/feat-m2-real-readonly-tools`
- 当前主分支：`main`
- 合并提交：`bf4aa04 feat: 接入 M2 真实只读工具`
- 已提交的 M2 检查点：
  - `9d5b49a docs: 启动 M2 真实只读工具实施`
  - `bbf2585 feat: 增加巡检原子生命周期与工具审计`
  - `cf82709 feat: 增加只读目标目录与工具安全网关`
  - `1a5330d feat: 接入真实只读工具与巡检编排`
  - `24a2c42 fix: 兼容云端只读契约差异`
  - `e76c8d9 docs: 更新HTTP契约探测状态`
  - `aced0de fix: 兼容SSH主机状态契约`
  - `5238f47 fix: 支持配置Kafka bootstrap`
  - `a8be87f docs: 更新M2云端探测交接`
  - `ee6222e fix: 正确归类缺失秘密配置`
  - `fa012ad fix: 归一Redis只读超时错误`
  - `437e607 fix: 归一数据库认证失败错误`
  - `1edb57e docs: 更新M2数据库与日志探测状态`
  - `916b6fe docs: 更新M2会话交接状态`
  - `5590c0e fix: 兼容Doris现场契约并完成Kline影子巡检`
  - `b5858c8 fix: 兼容Kafka与MySQL现场契约`
  - `74b838a docs: 更新M2远端同步状态`
  - `729cec8 docs: 完成M2收尾交接`

不要删除、重建或覆盖该 worktree。下个会话若看到未解释改动，先停止并确认来源。

## 2. 已完成的本地能力

- Inspection 生命周期：
  - 先保存 `running`。
  - Observation、Finding 和最终状态原子写入。
  - 失败时更新为 `failed`。
- `tool_invocations` SQLite 审计表和 Repository 接口。
- 目标 TOML 与秘密分离：
  - 示例：`config/targets.example.toml`
  - 真实 `config/targets.toml` 已加入 `.gitignore`
  - 密码只从环境变量读取。
- 统一参数/结果脱敏和稳定工具错误分类。
- 白名单工具网关和局部失败隔离。
- 受控传输：
  - HTTP：仅固定目标 GET、超时、一次有限重试、禁止重定向。
  - SSH：严格 known_hosts、`RejectPolicy`、固定命令目录。
  - MySQL 协议：固定只读查询目录和只读 Session。
  - Redis：无通用命令入口，仅暴露有限读方法。
- 组件适配器：
  - Flink Jobs、Job 详情、Checkpoint、反压。
  - Spring API 和 AI Engine 健康检查。
  - 主机资源与服务状态。
  - Kafka Topic、Offset 推进、Consumer Group 可见性。
  - Doris 数据新鲜度。
  - MySQL 规则表有限样本。
  - Redis INFO、DBSIZE、受限 SCAN 和有限 Key 样本。
  - 固定日志源的最近 200 行或 30 分钟日志。
- 真实巡检编排：
  - `PreparedDiagnosis`
  - `ReadOnlyInspectionPlanner`
  - `InspectionCollector`
  - `LiveInspectionService`
- CLI：

```bash
datasentry inspection run \
  --question "为什么K线不更新" \
  --targets-file config/targets.toml \
  --knowledge-root knowledge \
  --database-path var/datasentry-m2.db
```

## 3. 最近验证结果

在 M2 worktree 执行：

```bash
PYTHONPATH=src /Users/nate/Codex/data-sentry-agent/.venv/bin/pytest tests -q \
  -W error::ResourceWarning \
  --cov=datasentry \
  --cov-report=term-missing \
  --cov-fail-under=90

/Users/nate/Codex/data-sentry-agent/.venv/bin/ruff format --check .
/Users/nate/Codex/data-sentry-agent/.venv/bin/ruff check .
MYPYPATH=src /Users/nate/Codex/data-sentry-agent/.venv/bin/mypy src
git diff --check
```

最近结果：

- 182 个测试通过。
- 覆盖率 90.17%。
- Ruff 通过。
- mypy strict 通过。
- `git diff --check` 通过。
- 已执行 Flink REST、Spring API、AI Engine 固定 HTTP GET 只读契约探测。
- 已执行固定 SSH 白名单命令探测主机资源、时间同步、服务进程指纹和 Kafka Topic/Offset。
- 已按用户确认用临时测试密码做数据库/Redis 只读契约探测；密码只做进程内注入，未写入文件、未打印、未提交。
- 已执行 Kline 端到端只读影子巡检，9 个工具调用全部成功并持久化。
- 已执行 Kafka Consumer Group 和 MySQL 规则表固定工具复测。
- 尚未读取或保存任何生产秘密。

## 3.1 云端只读契约探测进度

- 已在 ignored `config/targets.toml` 中整理用户本机映射的 `data1`、`data2`、`data3` 目标，不提交该文件。
- 当前本机 ignored 目标配置要点：
  - `hosts.data1.address = "data1"`，用户本机将其映射到当前公网 IP。
  - data1/data2/data3 内网 IP 分别为 `192.168.1.10`、`192.168.1.20`、`192.168.1.30`。
  - HTTP：Flink `http://data1:8081`，Spring API `http://data1:8080`，AI Engine `http://data1:8000`。
  - Doris：`data1:9030`，当前 ignored 配置使用 `root`、无密码和 `streamlake` 库。
  - MySQL：`data1:3306`，当前 ignored 配置使用 `root` 和 `risk_control`。
  - Redis：`data1:6379`，DB 0，当前 ignored 配置使用 ACL 用户 `default`。
  - SSH：仅可丢弃测试实例临时使用 `root` + `/Users/nate/.ssh/datasentry_m2_disposable`。
  - known_hosts：`/Users/nate/.ssh/datasentry_known_hosts`，已由用户核对指纹。
  - Kafka bootstrap：`ssh.*.kafka_bootstrap = "data1:9092"`。
- Flink REST 已通过首轮现场探测：
  - `streamlake-kline-aggregation`、`streamlake-whale-cep`、`streamlake-risk-control` 均为 RUNNING。
  - Kline Job 详情、Checkpoint 和 Vertex Backpressure 固定接口可访问。
  - 现场 Backpressure 响应使用 `backpressureLevel` 与 `ok`，已补 fixture 并兼容解析。
- Spring API 已通过首轮现场探测：
  - `/actuator/health` 返回 UP。
  - `/api/kline/latest` 现场可返回空数组，已补 fixture 并将其识别为有效空结果。
- AI Engine 已通过首轮现场探测：
  - `/health` 返回 RUNNING normal。
- SSH 主机和服务状态已通过首轮现场探测：
  - 用户已核对 `data1`、`data2`、`data3` SSH host key。
  - 当前仅在可丢弃测试实例上临时使用 root key；生产或长期实例仍必须改为无 sudo、无写权限的只读用户。
  - 三台主机资源、inode、时间同步探测通过。
  - data1 的 Kafka、Flink JobManager、Doris FE、MySQL、Redis、Collector、Spring API、AI Engine 指纹为 RUNNING。
  - data2/data3 的 Flink TaskManager 和 Doris BE 指纹为 RUNNING。
- 现场 SSH 契约差异：
  - Ubuntu `df` 不允许 `df -i --output=...`，已改为 `df -i`。
  - `df -i` 可能返回 inode 使用率为 `-` 的行，已跳过不可排序行。
- Kafka 探测已部分通过：
  - Kafka 进程指纹为 RUNNING。
  - 现场确认 `127.0.0.1:9092` 从 data1 内部不可达，但 `data1:9092` 和 `192.168.1.10:9092` 可作为 Kafka bootstrap。
  - 已将 Kafka bootstrap 从硬编码 `127.0.0.1:9092` 改为 SSH 目标配置项 `kafka_bootstrap`。
  - Topic 列表和 broker 状态探测通过，可见 `binance.depth.raw`、`binance.trade.raw`、`streamlake.whale.alert`。
  - `binance.trade.raw` Offset 双采样显示正在推进，分区数为 6。
  - `flink-kline-group` Consumer Group 查询返回 `FIND_COORDINATOR` 超时，暂保留为上游未知，不包装成正常不可见。
- Doris 使用 root 无密码连接成功；`SHOW DATABASES` 可见 `streamlake`，`default` 库不存在。
- Doris `kline_1min`、`whale_alert`、`risk_trigger` 和 `ai_diagnosis` 固定新鲜度查询均通过。
- Doris 现场契约差异：
  - 新鲜度比较应使用数据库会话 `NOW()`，不能用 `UTC_TIMESTAMP()` 与本地业务时间列直接比较。
  - `whale_alert` 时间字段为 `alert_time`，不是 `event_time`。
  - `ai_diagnosis` 时间字段为 `create_time`，不是 `created_at`。
- MySQL 使用 root 测试密码可连接 `risk_control`；用户手工补回 `risk_rules` 和 `whale_thresholds` 后，固定样本工具复测通过；异常表 `RECOVER_YOUR_DATA_info` 根因仍未确认，未读取该表内容。
- Redis 使用 ACL 用户 `default` 和临时测试密码后固定样本工具通过，生成 `redis_info`、`redis_dbsize` 和 `redis_key_sample` Observation。
- `spring_api` 有限日志路径已发现为 `/opt/StreamLake-Binance/api-server/api.log`，固定日志工具通过，最近 30 分钟读取到 2 行。

## 3.2 本会话完成的代码/契约改动

前序会话不是只写文档，已经完成以下可验证改动：

- `src/datasentry/tools/adapters/api.py`
  - Spring `/api/kline/latest` 只读探针允许返回对象或列表。
  - 空对象/空列表都映射为 `api_read_probe.status = "empty"`。
  - 补充 fixture：`tests/fixtures/contracts/api/spring_kline_latest_empty.json`。
- `src/datasentry/tools/adapters/flink.py`
  - Backpressure 同时兼容 `backpressure-level` 与 `backpressureLevel`。
  - 全部 vertex 为 `ok` 时，聚合 `backpressure_level = "ok"`，不再误判为 `unknown`。
  - 补充 fixture：`tests/fixtures/contracts/flink/backpressure_ok_camel.json`。
- `src/datasentry/tools/transports/ssh.py`
  - `HOST_INODES` 固定命令从 `df -i --output=...` 改为 Ubuntu 兼容的 `df -i`。
  - Kafka CLI bootstrap 从硬编码 `127.0.0.1:9092` 改为 `SshTarget.kafka_bootstrap`。
- `src/datasentry/tools/adapters/host.py`
  - `df -i` 输出中 `IUse% = -` 的行跳过，避免解析崩溃。
- `src/datasentry/tools/targets.py`
  - 新增 `SshTarget.kafka_bootstrap`，默认 `127.0.0.1:9092`。
  - 校验格式为 `host:port`，端口必须在 1～65535。
- `config/targets.example.toml`
  - 示例 SSH 目标新增 `kafka_bootstrap = "127.0.0.1:9092"`。

对应提交：

- `24a2c42 fix: 兼容云端只读契约差异`
- `aced0de fix: 兼容SSH主机状态契约`
- `5238f47 fix: 支持配置Kafka bootstrap`

## 3.2.1 本会话完成的代码/契约改动

- `src/datasentry/tools/targets.py`
  - `MySqlTarget.password_env` 改为可选，支持 Doris root 无密码目标；配置秘密分离规则仍保留，设置了 `password_env` 的目标继续从环境变量读取。
- `src/datasentry/tools/transports/mysql.py`
  - 无 `password_env` 时使用空密码连接。
  - 数据库返回行允许保留 `datetime` 等数据库原生类型，由上层 adapter 转换为 Observation JSON 值。
  - 连接阶段 1049 归一为 `tool.configuration`。
  - 查询阶段 1054/1146 归一为 `tool.configuration`。
  - Doris 新鲜度固定查询改用 `NOW()`，并修正 `whale_alert.alert_time`、`ai_diagnosis.create_time` 字段名。
- `src/datasentry/tools/adapters/doris.py`、`src/datasentry/tools/adapters/mysql.py`
  - 同步数据库行协议类型，允许 adapter 接收数据库原生类型。
- 测试：
  - 增加无密码数据库目标、datetime 传输、未知库、缺失表和 Doris 现场字段名回归测试。

## 3.2.2 本会话 Kafka/MySQL 复测代码改动

- `src/datasentry/tools/transports/ssh.py`
  - Kafka Consumer Group 查询在 stdout 有有效结果且 stderr 仅为 `has no active members` warning 时不再失败。
- `src/datasentry/tools/adapters/kafka.py`
  - Consumer Group lag 改为按表头中的 `LAG` 列解析，兼容无 active members 时后续列为 `-` 的输出。
- `src/datasentry/tools/transports/mysql.py`
  - `risk_rules.max_single_qty` 和 `whale_thresholds.threshold_quote` 通过 SQL alias 统一为 `threshold`。
- `src/datasentry/tools/adapters/mysql.py`
  - MySQL `Decimal` 阈值转换为字符串后进入 Observation，避免数据库原生类型破坏 JSON 契约。
- 测试：
  - 增加 Kafka group warning、lag 表头解析、MySQL 现场列名 alias、Decimal 转 JSON 回归测试。

## 3.3 本会话云端探测事实

所有现场调用均为固定只读 HTTP GET、固定 SSH 白名单命令或固定 Kafka CLI 查询；没有执行启动、停止、重启、
改配置、补数、删除数据、Savepoint、自由 Shell 或自由 SQL。

已确认：

- Flink：
  - 三个 Job 均 RUNNING。
  - Kline Job 详情可读。
  - Kline Checkpoint 最新完成，连续失败数为 0。
  - Backpressure 明细为 ok，聚合后为 `ok`。
- Spring API：
  - `/actuator/health` 返回 UP。
  - `/api/kline/latest` 当前可返回 `[]`，作为有效空结果处理。
- AI Engine：
  - `/health` 返回 RUNNING normal。
- SSH/主机：
  - data1/data2/data3 host key 用户已核对。
  - 三台主机 uptime、memory、filesystem、inode、time sync 可读。
  - 时间同步均为 True。
- 服务指纹：
  - data1：Kafka、Flink JobManager、Doris FE、MySQL、Redis、Collector、Spring API、AI Engine 均 RUNNING。
  - data2/data3：Flink TaskManager、Doris BE 均 RUNNING。
- Kafka：
  - `data1:9092` 与 `192.168.1.10:9092` 可作为 data1 上 Kafka CLI bootstrap。
  - Topic 列表可读：`binance.depth.raw`、`binance.trade.raw`、`streamlake.whale.alert`。
  - `binance.trade.raw` Offset 正在推进，分区数为 6。
  - `flink-kline-group` 查询返回 `FIND_COORDINATOR` 超时；当前不要把它解释成“正常不可见”，只记录 unknown。

未完成：

- MySQL `risk_control.whale_thresholds`、`risk_control.risk_rules` 样本查询：当前表不存在，无法完成。
- MySQL 异常表 `RECOVER_YOUR_DATA_info` 的来源与业务表消失原因仍未确认。

## 3.4 本会话继续探测结果

- 重新确认 M2 worktree 干净，分支为 `feat/m2-real-readonly-tools`，最新交接提交为 `a8be87f`。
- 确认 ignored `config/targets.toml`、`/Users/nate/.ssh/datasentry_known_hosts` 和临时 SSH key 仍存在。
- 目标配置中当前别名为：
  - MySQL 协议目标：`doris`、`mysql`
  - Redis 目标：`redis`
  - 日志源：`spring_api`
- 当前 Codex 执行环境缺少：
  - `DATASENTRY_DORIS_PASSWORD`
  - `DATASENTRY_MYSQL_PASSWORD`
  - `DATASENTRY_REDIS_PASSWORD`
- 因缺少上述秘密环境变量，Doris、MySQL 和 Redis 单工具探测均在触网前稳定返回 `tool.configuration`，没有连接数据库或 Redis。
- 修复了一个本地契约问题：MySQL/Redis secret 缺失以前会被宽泛捕获为 `tool.connection_failed`，现在会在创建连接前返回 `tool.configuration`，并新增回归测试。
- 使用 `RecentLogsTool` 对 `spring_api` 执行固定文件日志读取，远端固定命令返回 stderr，工具归一为 `tool.upstream_error`；未使用自由 Shell 或自由日志路径。

## 3.5 临时测试密码探测结果

- 按用户提示，将同一临时测试密码仅注入本次 Python 进程的 `DATASENTRY_DORIS_PASSWORD`、`DATASENTRY_MYSQL_PASSWORD` 和 `DATASENTRY_REDIS_PASSWORD`，未写入文件、未提交、未打印。
- Doris `kline_1min` 固定新鲜度工具返回 `tool.authentication_failed`。
- MySQL `risk_rules` 固定样本工具返回 `tool.authentication_failed`。
- MySQL `whale_thresholds` 固定样本工具返回 `tool.authentication_failed`。
- Redis `risk:blacklist:*` 固定样本工具返回 `tool.timeout`。
- 现场 Redis 探测暴露 redis-py 懒连接异常未归一的问题；已补充 `ReadOnlyRedisClient` 命令级异常归一，Redis 超时现在稳定返回 `tool.timeout`，不再冒出 traceback。
- 现场 MySQL 协议握手诊断显示 Doris/MySQL 均为 `OperationalError` 1045；已补充连接阶段 1044/1045 到 `tool.authentication_failed` 的归一。
- 日志 stderr 诊断使用同一个固定 `tail` 白名单命令，确认当前配置路径不存在。

## 3.6 root/default 复测与日志发现

- 按用户确认，将 ignored `config/targets.toml` 临时调整为：
  - Doris：`root` / `default`
  - MySQL：`root` / `risk_control`
  - Redis：ACL 用户 `default`
  - `spring_api` 日志：`/opt/StreamLake-Binance/api-server/api.log`
- TCP 连通性：
  - `data1:9030`、`data1:3306`、`data1:6379` 均可连接。
- Doris：
  - 使用 root 测试密码，不指定库仍返回 1045，仍是认证/授权问题。
- MySQL：
  - root 测试密码不指定库连接成功。
  - `SHOW DATABASES` 可见 `risk_control`。
  - `risk_control` 内缺少 `risk_rules`、`whale_thresholds`，固定查询均返回 1146。
  - 当前只看到表 `RECOVER_YOUR_DATA_info`，未读取该表内容；该表名异常，应优先人工核查数据库状态或备份。
- Redis：
  - TCP 已放通。
  - 用户名 `root` 认证失败；用户名 `default` 认证成功。
  - 固定 `get_redis_key_sample` 工具通过，返回 `redis_info`、`redis_dbsize`、`redis_key_sample`。
- 日志：
  - 只读查找发现 `/opt/StreamLake-Binance/api-server/api.log`。
  - 固定 `get_recent_logs(spring_api)` 工具通过，最近 30 分钟读取到 2 行。

## 3.7 Doris 无密码与 MySQL 异常表复测

- 用户确认 Doris 无密码、MySQL/Redis 测试密码一致，Kafka Consumer Group 原因暂不清楚，先存疑。
- Doris：
  - `root` 无密码可连接 `data1:9030`。
  - `default` 库不存在，底层错误为 1049，已归一为 `tool.configuration`。
  - `SHOW DATABASES` 可见 `streamlake`，已将 ignored `config/targets.toml` 中 Doris database 改为 `streamlake`。
  - `kline_1min` 固定新鲜度工具通过，现场样本新鲜度约几十秒。
  - `whale_alert` 固定查询原字段 `event_time` 不存在，实际字段为 `alert_time`，已修正。
  - `risk_trigger` 固定新鲜度工具通过。
  - `ai_diagnosis` 固定查询原字段 `created_at` 不存在，实际字段为 `create_time`，已修正；现场最新时间停留在 2026-05-08，作为事实保留。
  - Doris `NOW()` 与业务时间列同一会话时区；`UTC_TIMESTAMP()` 会导致本地业务时间被误判为 clock skew，固定查询已改用 `NOW()`。
- MySQL：
  - 使用 root 和测试密码连接 `risk_control` 成功。
  - `risk_rules` 与 `whale_thresholds` 固定样本查询均返回 1146 表不存在；已归一为 `tool.configuration`。
  - `SHOW TABLES` 仅见 `RECOVER_YOUR_DATA_info`；未读取该表内容。
  - 该状态高度可疑，应优先人工核查实例安全组、MySQL 账户、root 密码、备份和应用配置来源。

## 3.7.1 Kafka Group 与 MySQL 规则表复测

- 用户确认 Kafka 原因：
  - 当前为不依赖 ZooKeeper 的新版单节点 Kafka。
  - 内部 Topic 副本配置与单节点部署不匹配。
  - 最初修改了错误的实际启动配置文件。
  - 修正后 `__consumer_offsets` 已创建，Consumer Group Coordinator 恢复。
- 固定 `get_kafka_group(data1, flink-kline-group)` 复测通过：
  - `consumer_group_visibility = VISIBLE`
  - `consumer_group_lag` 可读取；现场样本 lag 为几十到百级，随采样时间变化。
  - Kafka CLI 会在 stderr 输出 `Consumer group 'flink-kline-group' has no active members.`，但 stdout 同时包含有效 lag 表；代码已只对该特定 warning 放行。
- 用户已手工补回 MySQL `risk_rules` 和 `whale_thresholds`。
- 固定 `get_mysql_table_sample(mysql, risk_rules)` 复测通过，现场样本行数为 5。
- 固定 `get_mysql_table_sample(mysql, whale_thresholds)` 复测通过，现场样本行数为 7。
- 现场列名为：
  - `risk_rules.max_single_qty`
  - `whale_thresholds.threshold_quote`
  - 代码已统一 alias 为 Observation 中的 `threshold`。

## 3.8 Kline 端到端只读影子巡检结果

执行：

```bash
/Users/nate/Codex/data-sentry-agent/.venv/bin/datasentry inspection run \
  --question "为什么K线不更新" \
  --targets-file config/targets.toml \
  --knowledge-root knowledge \
  --database-path var/datasentry-m2-shadow.db
```

结果：

- Inspection `f8a6243a-1db9-4722-bb48-9beb9958b86d` 为 `completed`。
- 9 个工具调用全部 `succeeded`：
  - `get_host_status(data1)`
  - `get_service_status(data1, collector)`
  - `get_flink_jobs(flink)`
  - `get_flink_job(flink, kline)`
  - `get_flink_checkpoints(flink, kline)`
  - `get_flink_backpressure(flink, kline)`
  - `get_kafka_topic(data1, binance.trade.raw)`
  - `get_doris_table_freshness(doris, kline_1min)`
  - `get_api_health(spring_api)`
- 关键 Observation：
  - Kafka `binance.trade.raw` 正在推进。
  - Kline Job 为 RUNNING。
  - Checkpoint 连续失败数为 0。
  - Backpressure 为 `ok`。
  - Doris `kline_1min` 新鲜度约 1 分钟。
  - Spring API `/api/kline/latest` 返回有效空结果 `empty`。
- 诊断结论已从误导性的“Observation 不足”修正为“K线主链路当前正在推进”。
- 如果用户仍观察到页面 K 线不更新，下一步应检查 Spring API 查询参数、缓存、前端轮询和页面状态，而不是 Collector → Kafka → Flink → Doris 主链路。

## 4. 下一会话开始步骤

新会话首先读取：

1. `AGENTS.md`
2. `docs/PROJECT_STATUS.md`
3. `docs/M2_HANDOFF.md`
4. `docs/superpowers/plans/2026-06-25-m2-real-readonly-tools.md`

然后进入：

```bash
cd /Users/nate/Codex/data-sentry-agent/.worktrees/feat-m2-real-readonly-tools
git status --short --branch
git diff --check
```

先确认工作树干净，再检查第 6 节所需云端条件。若代码或契约 fixture 有新修改，
应先按第 3 节重新运行全量验证并创建稳定提交。

## 5. Git 检查要求

云端探测产生代码、fixture 或文档修改后，提交前必须检查 staged diff 不包含：

- 真实密码、Token、Cookie、AK/SK 或私钥。
- `config/targets.toml`。
- 真实生产日志。
- `.env`。

暂时不要合并到 `main`。云端契约探测可能暴露实际字段、路径和版本差异，
应先在当前功能分支继续修正。

## 6. 现在需要用户准备的云端条件

用户可开启可丢弃实例，但不更新备份镜像。准备：

- SSH 主机/IP 和端口。
- 无 sudo、无写权限的 SSH 用户名。
- SSH 私钥在用户本机的路径；不要发送私钥内容。
- 可信 known_hosts 文件。
- Doris/MySQL 只读账号：
  - 只允许 `SELECT`、`SHOW`、`DESCRIBE`。
- Redis ACL 账号：
  - 只允许计划中的读命令。
  - 禁止 `KEYS` 和写命令。
- Flink、Spring API、AI Engine 的内网访问地址。

密码和 Token 不发送到聊天，不写入 TOML，通过本机环境变量设置：

```bash
export DATASENTRY_DORIS_PASSWORD='...'
export DATASENTRY_MYSQL_PASSWORD='...'
export DATASENTRY_REDIS_PASSWORD='...'
```

如果 SSH 使用密码，同样只通过目标文件声明环境变量名，不在 Git 中保存值。

## 7. 云端契约探测顺序

不要直接先跑完整巡检。按以下顺序逐项验证：

1. Flink REST
   - `/jobs/overview`
   - Job 详情
   - Checkpoint
   - Vertex 反压
2. Spring API / AI Engine
   - 健康路径是否与 fixture 一致
   - Kline 只读探针路径及返回结构
   - AI 降级响应中 Milvus 字段
3. SSH 与主机
   - known_hosts 和只读账号
   - `uptime`、`free`、`df`、`timedatectl`
   - 固定服务进程指纹是否符合实际
4. Kafka
   - `/opt/kafka/bin` 是否为真实路径
   - Topic list/describe/get-offsets 输出格式
   - Consumer Group 不可见时的实际 stderr/退出行为
5. Doris
   - 数据库名、表名和时间字段
   - 返回时区
6. MySQL
   - `whale_thresholds`、`risk_rules` 实际列名
7. Redis
   - ACL 是否允许 INFO、DBSIZE、SCAN、TYPE、TTL、GET
8. 有限日志
   - 真实日志路径或 systemd unit
   - 输出是否包含需要新增脱敏的字段

每项只执行只读调用。发现实际契约差异时：

- 先保存脱敏响应。
- 更新 `tests/fixtures/contracts/`。
- 先写失败测试，再修改解析器。
- 不临时开放自由 Shell、自由 SQL 或自由日志路径。

## 8. 完整影子巡检

所有单工具契约通过后才运行：

```bash
datasentry inspection run \
  --question "为什么K线不更新" \
  --targets-file config/targets.toml \
  --knowledge-root knowledge \
  --database-path var/datasentry-m2-shadow.db
```

验收：

- Inspection 为 `completed`。
- 每个工具有 `tool_invocations` 审计。
- 成功 Observation 带 UTC 时间、来源和目标。
- 单个工具失败只形成 unknown。
- SQLite、stdout、stderr 和日志中没有秘密。
- 没有执行任何写操作。

## 9. 云端验证后的收尾

1. 将脱敏真实响应补充到契约 fixture。
2. 运行全量测试、Ruff、mypy 和秘密扫描。
3. 更新 `README.md` 和 `docs/PROJECT_STATUS.md`：
   - 已现场验证的工具。
   - 未验证项。
   - Kafka Group、日志路径、Doris/Flink 配置的新发现。
4. 创建里程碑提交。
5. `git fetch origin` 并检查分叉。
6. 推送 `feat/m2-real-readonly-tools`。
7. 创建 PR，但未经用户批准不合并。

## 10. 已知注意事项

- 当前工具计划重点覆盖 Kline 端到端链路，并已增加组件状态、Whale/Risk
  Flink、Doris 和 Redis 的基础映射；云端后应继续核对四类问题是否都形成
  足够的真实 Observation。
- Flink Job 名、Spring 健康路径、Doris 时间列、Kafka CLI 输出和服务进程
  指纹目前依据知识库与脱敏 fixture，必须现场确认。
- Kafka Consumer Group 不可见不能解释为正常，也不能生成 `lag=0`。
- Milvus 不可用是允许的 AI Engine 降级状态。
- `/root/bin/*.sh` 尚未审计，不得调用。
- 不得降低 90% 覆盖率门槛。
