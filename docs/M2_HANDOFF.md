# M2 真实只读工具交接说明

更新时间：2026-06-26

## 0. 当前阶段

M2 本地实现已完成全量验证，当前进入云端只读契约探测阶段。开始现场探测前必须：

1. 进入现有 M2 worktree。
2. 确认工作树干净。
3. 确认本机 ignored `config/targets.toml`、秘密环境变量和 known_hosts 已准备。
4. 按本文第 6、7 节逐项执行只读探测，不直接运行完整巡检。

不得在工作树存在未解释修改时开始云端适配，也不得丢弃、重置或覆盖该 worktree。

## 1. 当前工作位置

- 主仓库：`/Users/nate/Codex/data-sentry-agent`
- M2 worktree：`/Users/nate/Codex/data-sentry-agent/.worktrees/feat-m2-real-readonly-tools`
- 当前分支：`feat/m2-real-readonly-tools`
- 基线：`main` / `origin/main` 为 `5fa055c`
- 已提交的 M2 检查点：
  - `9d5b49a docs: 启动 M2 真实只读工具实施`
  - `bbf2585 feat: 增加巡检原子生命周期与工具审计`
  - `cf82709 feat: 增加只读目标目录与工具安全网关`

`cf82709` 之后的组件适配器、编排、CLI、测试和文档已形成稳定检查点。
不要删除、重建或覆盖该 worktree。

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

- 161 个测试通过。
- 覆盖率 90.22%。
- Ruff 通过。
- mypy strict 通过。
- `git diff --check` 通过。
- 已执行 Flink REST 与 Spring API 固定 HTTP GET 只读契约探测。
- 尚未使用 SSH、数据库或 Redis 凭据。
- 尚未读取或保存任何生产秘密。

## 3.1 云端只读契约探测进度

- 已在 ignored `config/targets.toml` 中整理用户本机映射的 `data1`、`data2`、`data3` 目标，不提交该文件。
- Flink REST 已通过首轮现场探测：
  - `streamlake-kline-aggregation`、`streamlake-whale-cep`、`streamlake-risk-control` 均为 RUNNING。
  - Kline Job 详情、Checkpoint 和 Vertex Backpressure 固定接口可访问。
  - 现场 Backpressure 响应使用 `backpressureLevel` 与 `ok`，已补 fixture 并兼容解析。
- Spring API 已通过首轮现场探测：
  - `/actuator/health` 返回 UP。
  - `/api/kline/latest` 现场可返回空数组，已补 fixture 并将其识别为有效空结果。
- AI Engine `data1:8000` 从本机访问超时，尚未完成健康契约探测；需要确认进程监听地址、安全组和防火墙。
- SSH、Kafka、Doris、MySQL、Redis 和日志探测尚未开始，仍需可信 known_hosts、专用只读账号和本机环境变量。

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
