# M2 真实只读工具交接说明

更新时间：2026-06-26

## 0. 当前阶段

M2 本地实现已完成全量验证，当前处于云端只读契约探测中段。HTTP、SSH 主机/服务状态、
Kafka Topic/Offset 已完成首轮现场契约探测；Doris、MySQL、Redis 仍缺本机秘密环境变量，
日志已执行固定文件日志命令但当前日志源返回 `tool.upstream_error`。
下个会话开始现场探测前必须：

1. 进入现有 M2 worktree。
2. 确认工作树干净。
3. 确认本机 ignored `config/targets.toml`、known_hosts 和临时测试 SSH key 仍存在。
4. 继续按本文第 7 节从 Doris/MySQL/Redis/日志逐项执行只读探测，不直接运行完整巡检。

不得在工作树存在未解释修改时开始云端适配，也不得丢弃、重置或覆盖该 worktree。

## 0.1 下个会话最短恢复摘要

下个会话不用让用户解释 Git 或本轮进度，直接读取本文件后执行：

```bash
cd /Users/nate/Codex/data-sentry-agent/.worktrees/feat-m2-real-readonly-tools
git status --short --branch
git log --oneline -8
git diff --check
```

当前已知状态：

- 分支：`feat/m2-real-readonly-tools`
- 本轮交接文档提交：`docs: 更新M2云端探测交接`；实际 hash 以 `git log -1 --oneline` 为准。
- 最近功能检查点：
  - `5238f47 fix: 支持配置Kafka bootstrap`
  - `aced0de fix: 兼容SSH主机状态契约`
  - `e76c8d9 docs: 更新HTTP契约探测状态`
  - `24a2c42 fix: 兼容云端只读契约差异`
  - `1a5330d feat: 接入真实只读工具与巡检编排`
- GitHub 同步状态：当前功能分支尚未推送到 GitHub。
- 当前本地工作树在本次交接提交后应保持干净；`config/targets.toml`、`var/`、缓存目录为 ignored。
- 下一步不要先跑完整巡检；优先补齐 Doris、MySQL、Redis 本机秘密环境变量，并确认 `spring_api` 日志源路径或 systemd unit。
- Kafka Consumer Group `flink-kline-group` 当前 `FIND_COORDINATOR` 超时，可先记录为 unknown，不阻塞 Kline 首个场景。

## 1. 当前工作位置

- 主仓库：`/Users/nate/Codex/data-sentry-agent`
- M2 worktree：`/Users/nate/Codex/data-sentry-agent/.worktrees/feat-m2-real-readonly-tools`
- 当前分支：`feat/m2-real-readonly-tools`
- 基线：`main` / `origin/main` 为 `5fa055c`
- 已提交的 M2 检查点：
  - `9d5b49a docs: 启动 M2 真实只读工具实施`
  - `bbf2585 feat: 增加巡检原子生命周期与工具审计`
  - `cf82709 feat: 增加只读目标目录与工具安全网关`
  - `1a5330d feat: 接入真实只读工具与巡检编排`
  - `24a2c42 fix: 兼容云端只读契约差异`
  - `e76c8d9 docs: 更新HTTP契约探测状态`
  - `aced0de fix: 兼容SSH主机状态契约`
  - `5238f47 fix: 支持配置Kafka bootstrap`

`5238f47` 之后本文件会再有一个交接文档提交。不要删除、重建或覆盖该 worktree。

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

- 167 个测试通过。
- 覆盖率 90.13%。
- Ruff 通过。
- mypy strict 通过。
- `git diff --check` 通过。
- 已执行 Flink REST、Spring API、AI Engine 固定 HTTP GET 只读契约探测。
- 已执行固定 SSH 白名单命令探测主机资源、时间同步、服务进程指纹和 Kafka Topic/Offset。
- 尚未使用数据库或 Redis 凭据。
- 尚未读取或保存任何生产秘密。

## 3.1 云端只读契约探测进度

- 已在 ignored `config/targets.toml` 中整理用户本机映射的 `data1`、`data2`、`data3` 目标，不提交该文件。
- 当前本机 ignored 目标配置要点：
  - `hosts.data1.address = "data1"`，用户本机将其映射到当前公网 IP。
  - data1/data2/data3 内网 IP 分别为 `192.168.1.10`、`192.168.1.20`、`192.168.1.30`。
  - HTTP：Flink `http://data1:8081`，Spring API `http://data1:8080`，AI Engine `http://data1:8000`。
  - Doris：`data1:9030`，数据库暂按 `streamlake`。
  - MySQL：`data1:3306`，数据库暂按 `risk_control`。
  - Redis：`data1:6379`，DB 0。
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
- Doris、MySQL、Redis 因本机缺少 `DATASENTRY_DORIS_PASSWORD`、`DATASENTRY_MYSQL_PASSWORD`、`DATASENTRY_REDIS_PASSWORD` 尚未触网。
- `spring_api` 有限日志探测已通过固定 `tail` 命令触达远端，但当前配置日志源返回 `tool.upstream_error`，需要确认真实日志路径或改为登记的 systemd unit。

## 3.2 本会话完成的代码/契约改动

本会话不是只写文档，已经完成以下可验证改动：

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

- Doris `kline_1min` 新鲜度查询。
- MySQL `risk_control.whale_thresholds`、`risk_control.risk_rules` 样本查询。
- Redis INFO / DBSIZE / SCAN / TYPE / TTL / GET。
- 有限日志路径或 systemd unit 验证：当前 `spring_api` 文件日志源返回 `tool.upstream_error`。
- 完整 `datasentry inspection run` 影子巡检。

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
