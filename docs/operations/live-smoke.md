# DataSentry 真实只读巡检运维手册

本文档说明如何在不提交 secret、不执行生产写操作的前提下，运行 DataSentry live smoke。

## 适用范围

live smoke 只用于现场只读确认，允许执行：

- 固定 HTTP GET。
- 固定 SSH 白名单命令。
- 固定 Doris/MySQL 只读查询。
- 固定 Redis 只读采样。
- SQLite 巡检记录、Incident、RCA 和 Markdown export。

live smoke 不允许执行：

- 任意 Shell。
- 自动重启。
- 自动补数。
- 自动 Savepoint 恢复。
- 自动修改生产配置。
- 删除数据或写入生产数据库。

## 预检

先确认目标配置和本地 secret 注入状态：

```bash
datasentry ops preflight \
  --targets-file config/targets.toml
```

输出只展示变量名和状态：

- `configured`：当前 DataSentry 进程环境中存在该变量。
- `missing`：当前 DataSentry 进程环境中没有该变量，相关工具会在触网前返回配置缺失。

预检不会读取、打印或保存 secret 值。

## 变量命名

云端 StreamLake 作业和本地 DataSentry 巡检可能使用不同变量名。

| 用途 | 云端常见变量 | DataSentry 目标配置变量 |
|---|---|---|
| Doris | `DORIS_PASSWORD` | `DATASENTRY_DORIS_PASSWORD` |
| MySQL | `MYSQL_PASSWORD` | `DATASENTRY_MYSQL_PASSWORD` |
| Redis | `REDIS_PASSWORD` | `DATASENTRY_REDIS_PASSWORD` |

K 线巡检通常会读取 Doris freshness，因此缺 Doris secret 会先暴露。MySQL 和 Redis 只有在问题路由需要风控表、阈值表或黑名单证据时才会被调用；没有被调用时不会要求它们的密码。

## 推荐方式

长期运维应为 DataSentry 准备专用只读账号，并在运行 DataSentry 的服务环境中设置 `DATASENTRY_*` 变量。数据库账号只允许 `SELECT`、`SHOW` 和 `DESCRIBE`；Redis ACL 只允许计划内只读命令。

## 应急一次性映射

如果需要从本地临时复跑 live smoke，可以在单次命令进程中把云端 root-only secret 映射为 `DATASENTRY_*`。示例只展示模式，不包含真实密码：

```bash
DATASENTRY_DORIS_PASSWORD="$(
  ssh root@data1 "awk -F= '/^DORIS_PASSWORD=/{print substr(\$0, index(\$0,\"=\")+1)}' /root/.streamlake-secrets"
)" \
DATASENTRY_MYSQL_PASSWORD="$(
  ssh root@data1 "awk -F= '/^MYSQL_PASSWORD=/{print substr(\$0, index(\$0,\"=\")+1)}' /root/.streamlake-secrets"
)" \
DATASENTRY_REDIS_PASSWORD="$(
  ssh root@data1 "awk -F= '/^REDIS_PASSWORD=/{print substr(\$0, index(\$0,\"=\")+1)}' /root/.streamlake-secrets"
)" \
datasentry inspection run \
  --question "为什么K线不更新" \
  --targets-file config/targets.toml \
  --knowledge-root knowledge \
  --database-path var/datasentry-live-smoke.db
```

执行前注意：

- 不要在终端中 `echo` secret。
- 不要把真实值写入 `config/targets.toml`、`.env`、README、Issue、PR 或提交历史。
- 命令结束后，secret 只存在于该命令及其子进程环境中。
- 如果只需要 K 线巡检，可以只映射 `DATASENTRY_DORIS_PASSWORD`。

## 常见判断

`tool.configuration` 且提示缺少 `DATASENTRY_DORIS_PASSWORD`，表示本地 DataSentry 进程缺少 Doris secret，不等于云端 Flink Job 或 Spring API 没有 Doris 密码。

`tool.authentication_failed` 表示已经触达数据库或 Redis，但账号、密码或授权失败。此时应检查账号权限、Doris/MySQL/Redis 用户名和密码是否匹配。

`tool.connection_failed` 或 `tool.timeout` 表示网络、端口、服务状态或超时问题，需要结合主机、Collector、Kafka、Flink、Doris、Spring API 和 AI Engine 的只读证据判断。

## 结束后检查

运行完成后记录：

- Inspection id。
- 结论摘要。
- 失败工具及错误码。
- Doris freshness、Flink checkpoint、Kafka offset 和 API 固定读探针结果。
- 本次是否使用一次性 secret 映射。

不要记录真实 secret 值。
