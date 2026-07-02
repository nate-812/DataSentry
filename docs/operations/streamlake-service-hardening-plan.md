# StreamLake 服务低权限迁移方案

本文档用于规划 Spring API 和 AI Engine 从 root/手工进程形态迁移到专用服务用户、systemd 管理和 loopback/内网监听。它不是可直接复制执行的 service 文件；下次 `data1` 打开后必须先做只读确认，再由用户确认是否执行任何变更。

## 使用边界

- 不开云端实例时只维护本方案，不执行 SSH、不访问生产端口、不修改 systemd、不移动文件。
- 不以 root 长期运行 Spring API 或 AI Engine。
- 不现场编译未验证代码，不自动拉取新代码，不自动重启生产组件。
- 不打印真实 secret，不把 EnvironmentFile 内容写入日志、RCA、状态文档或 Git。
- 不开放生产写 Runbook；所有 systemd、目录权限、监听地址和 secret 注入方式变更都需要用户确认。

## 迁移前只读确认

维护窗口开始后，先记录以下事实：

| 项目 | Spring API | AI Engine |
|---|---|---|
| 当前进程命令 | 记录脱敏命令、进程用户和工作目录 | 记录脱敏命令、进程用户和工作目录 |
| 当前监听地址 | 记录 8080 是否为 `0.0.0.0`、`*`、内网或 `127.0.0.1` | 记录 8000 是否为 `0.0.0.0`、`*`、内网或 `127.0.0.1` |
| 构建产物路径 | 记录 jar、配置目录和日志路径 | 记录 Python/uvicorn 入口、venv、模型或配置目录 |
| secret 注入方式 | 记录变量名和文件权限，不记录值 | 记录变量名和文件权限，不记录值 |
| 健康检查 | 记录 API health 和 K 线固定读探针 | 记录 `/health` |

如果当前事实与方案假设不一致，先更新本方案或证据记录，不继续执行迁移。

## Spring API 目标形态

- 使用专用服务用户 `streamlake-api`，systemd 中设置 `User=streamlake-api` 和专用工作目录。
- 使用已验证构建产物，不现场编译，不从运行目录直接构建。
- 监听 `127.0.0.1` 或受控内网地址；公网访问通过用户确认的反向代理、内网或 SSH tunnel。
- 使用 `EnvironmentFile=` 指向 root-only 或服务可读的受限配置文件，文件中只保存运行所需变量。
- 日志输出到受控日志目录，日志不得打印数据库密码、token、Cookie 或完整连接串。

## AI Engine 目标形态

- 使用专用服务用户 `streamlake-ai`，systemd 中设置 `User=streamlake-ai` 和专用工作目录。
- 使用固定 Python 环境或容器入口，避免手工 nohup 进程长期运行。
- 监听 `127.0.0.1:8000` 或受控内网地址，不直接暴露公网。
- 使用 `EnvironmentFile=` 注入模型、数据库和外部 API 所需变量；只记录变量名和 configured/missing 状态。
- health 以 `curl -fsS http://127.0.0.1:8000/health` 为基础验证入口。

## systemd 设计约束

目标 unit 草案必须满足：

- `User=streamlake-api` 或 `User=streamlake-ai`，不使用 root 作为长期运行用户。
- `WorkingDirectory=` 指向受控发布目录，不指向 Git 工作区中的临时构建目录。
- `EnvironmentFile=` 指向受限配置文件，unit 文件本身不包含真实 secret。
- `Restart=` 策略必须先经用户确认，避免自动重启掩盖真实故障。
- `ExecStart=` 使用明确构建产物或入口，不调用 `/root/bin/spring.sh`、`/root/bin/ai.sh`、`xcall` 或 `xsync`。
- unit 启用前必须记录旧进程管理方式和回滚步骤。

## 回滚边界

- 迁移失败时只恢复 Spring API 或 AI Engine 本组件的上一版启动方式和网络入口。
- 不回滚数据库密码轮换，不删除 Kafka、Doris、MySQL、Redis 或 SQLite 数据。
- 不在回滚中引入现场编译、任意 Shell、任意 SQL、自动补数、自动改配置或自动 Savepoint 恢复。
- 如果 health 失败，先恢复上一版入口或进程，再记录失败项和未验证项。

## 变更后验证

Spring API 迁移后至少记录：

```bash
curl -fsS http://127.0.0.1:8080/api/health
curl -fsS 'http://127.0.0.1:8080/api/kline/BTCUSDT?interval=1min&limit=1'
```

AI Engine 迁移后至少记录：

```bash
curl -fsS http://127.0.0.1:8000/health
```

全局回归至少记录：

```bash
datasentry monitoring alert-smoke --config-file /etc/datasentry/monitoring.toml --payload-file tests/fixtures/alertmanager/kline_freshness_firing.json
datasentry inspection run --question "为什么K线不更新" --targets-file /etc/datasentry/targets.toml --knowledge-root knowledge --database-path /var/lib/datasentry/datasentry.db
```

所有结果写入 `docs/operations/maintenance-evidence-record.md` 对应格式，只记录状态、ID、脱敏摘要和未验证项。
