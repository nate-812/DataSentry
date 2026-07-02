# StreamLake 启停总控脚本

`deploy/ops/streamlake-startup.sh` 是给人工维护窗口使用的 StreamLake 启停编排脚本。它解决手工依次执行 `kafka.sh`、`doris.sh`、`flink.sh`、`spring.sh`、`ai.sh`、`job.sh` 和监控栈 `docker compose` 的繁琐问题。

它不是 DataSentry Runbook，不进入 DataSentry 自动执行白名单，不打印真实 secret，不自动 cancel Flink Job。

## 安装

从已同步的 DataSentry 仓库安装到云端 root 维护命令：

```bash
cd /opt/datasentry-agent
sudo install -o root -g root -m 0750 deploy/ops/streamlake-startup.sh /root/bin/streamlake-startup
```

也可以不安装，直接在仓库中执行：

```bash
cd /opt/datasentry-agent
sudo deploy/ops/streamlake-startup.sh status
```

## 命令

```bash
streamlake-startup plan start
streamlake-startup plan stop
streamlake-startup status
streamlake-startup start
streamlake-startup stop
streamlake-startup restart
```

- `plan start`：只展示启动顺序，不执行。
- `plan stop`：只展示关闭顺序，不执行。
- `status`：查看 Kafka、Doris、Flink、Spring API、AI Engine、DataSentry 监控栈和 Flink Job 状态。
- `start`：执行启动流程。
- `stop`：执行关闭流程。
- `restart`：先执行 `stop`，再执行 `start`。

## 启动顺序

`streamlake-startup start` 的顺序：

1. `/root/bin/kafka.sh start`
2. `/root/bin/doris.sh start`
3. `/root/bin/flink.sh start`
4. `/root/bin/spring.sh start`
5. `/root/bin/ai.sh start`
6. `cd /opt/datasentry-monitoring && docker compose start`
7. `/root/bin/job.sh all`

执行 `/root/bin/job.sh all` 前，脚本会通过 Flink CLI 检查固定三条 Job：

- `streamlake-kline-aggregation`
- `streamlake-whale-cep`
- `streamlake-risk-control`

如果三条都已经在运行，跳过提交。如果只发现部分 Job 在运行，脚本会停止并要求人工检查，避免重复提交造成脏状态。

## 关闭顺序

`streamlake-startup stop` 的顺序：

1. `cd /opt/datasentry-monitoring && docker compose stop`
2. `/root/bin/spring.sh stop`
3. `/root/bin/ai.sh stop`
4. `/root/bin/flink.sh stop`
5. `/root/bin/doris.sh stop`
6. `/root/bin/kafka.sh stop`

脚本不单独执行 Flink Job cancel。关闭 Flink 集群后 Job 会随集群停止；如果未来需要“只取消作业但不关集群”，应单独设计更明确的人工命令。

## 路径覆盖

默认路径：

```bash
STREAMLAKE_ROOT_BIN=/root/bin
STREAMLAKE_MONITORING_DIR=/opt/datasentry-monitoring
STREAMLAKE_FLINK_BIN=/opt/flink/bin/flink
```

测试或临时验证时可以覆盖：

```bash
STREAMLAKE_ROOT_BIN=/tmp/fake-root-bin \
STREAMLAKE_MONITORING_DIR=/tmp/fake-monitoring \
STREAMLAKE_FLINK_BIN=/tmp/fake-flink \
deploy/ops/streamlake-startup.sh plan start
```

## 安全边界

- 只用于人工维护窗口。
- 不进入 DataSentry 自动执行白名单。
- 不开放生产写 Runbook。
- 不打印真实 secret。
- 不读取或展示 `/root/.streamlake-secrets` 内容。
- 任一启动或关闭步骤失败时，脚本停止，不继续执行后续步骤。
