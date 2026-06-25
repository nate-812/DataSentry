# 运维入口与操作规范

## 1. 已发现的运维脚本

所有脚本位于data1的`/root/bin`。现有资料只确认了用途和表面命令，尚未完成源码级安全审计。

### `flink.sh`

| 命令 | 作用 | 默认权限 |
|---|---|---|
| `flink.sh status` | 检查JM和data2/data3 TM状态 | 自动只读 |
| `flink.sh start` | 启动Standalone集群 | 人工确认 |
| `flink.sh stop` | 停止集群 | 高风险审批 |

### `kafka.sh`

| 命令 | 作用 | 默认权限 |
|---|---|---|
| `kafka.sh status` | 检查Kafka进程和端口 | 自动只读 |
| `kafka.sh start` | 后台启动KRaft Kafka | 人工确认 |
| `kafka.sh stop` | 停止Kafka并等待退出 | 高风险审批 |

### `doris.sh`

| 命令 | 作用 | 默认权限 |
|---|---|---|
| `doris.sh status` | 跨节点检查FE/BE | 自动只读 |
| `doris.sh start` | 启动data1 FE和data2/data3 BE | 人工确认 |
| `doris.sh stop` | 停止Doris集群 | 高风险审批 |

### `job.sh`

| 命令 | 作用 | 默认权限 |
|---|---|---|
| `job.sh all` | 编译并提交三个Job | 人工确认 |
| `job.sh k` | 提交Kline Job | 人工确认 |
| `job.sh w` | 提交Whale Job | 人工确认 |
| `job.sh r` | 提交Risk Job | 人工确认 |

调用前必须检查是否已有同名Job，否则可能重复提交。

### `spring.sh`

| 命令 | 作用 | 默认权限 |
|---|---|---|
| `spring.sh status` | 检查进程/PID | 自动只读 |
| `spring.sh logs` | 查看日志 | 自动但限制行数 |
| `spring.sh start` | 构建并启动 | 人工确认 |
| `spring.sh restart` | 重启 | 人工确认 |
| `spring.sh stop` | 停止并清理PID | 高风险审批 |

脚本据称使用`.pid`防重入并按需Maven构建，仍需源码验证。

### `ai.sh`

| 命令 | 作用 | 默认权限 |
|---|---|---|
| `ai.sh status` | 检查Uvicorn状态 | 自动只读 |
| `ai.sh logs` | 查看AI日志 | 自动但限制行数 |
| `ai.sh start` | 激活`.venv`并启动 | 人工确认 |
| `ai.sh restart` | 重启 | 人工确认 |
| `ai.sh stop` | 停止服务 | 高风险审批 |

脚本会注入模型和Milvus环境变量，输出和日志必须脱敏。

### `init_data1.sh`

作用：

- 修改主机名。
- 配置`192.168.1.10/24`静态网络。
- 应用Netplan。
- 清理历史SSH免密指纹缓存。

这是破坏性初始化脚本，Agent默认禁止执行。

## 2. 构建与启动线索

### Flink

```text
mvn -q -DskipTests package
→ 生成JAR
→ 上传或使用服务器源码产物
→ flink run -d -c <入口类> <JAR>
```

实际生产优先使用已审计的`job.sh`，但提交前必须检查已有Job和JAR版本。

### Collector

历史启动方式线索：

```text
cd /opt/StreamLake-Binance/collector
source .venv/bin/activate
nohup python main.py ...
```

仓库存在`streamlake-collector.service.example`，说明曾设计systemd托管；服务器巡检时Collector仍是手工进程，不能把示例Unit当作已安装服务。

### Spring API

历史启动方式线索：

```text
java -jar <api-server jar>
```

### AI Engine

历史启动方式线索：

```text
cd /opt/StreamLake-Binance/ai-engine
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000
```

上述只是线索；Agent不得绕过现有脚本直接拼接命令执行。

## 3. 高风险补数工具

`scripts/backfill_klines.py`：

- 从Binance REST拉取历史K线。
- 使用`executemany`直接写Doris。
- 没有自动回滚。
- 发生脏写后只能设计并审批Doris删除方案。
- 风险等级：高。
- 第一版Agent禁止自动执行。

## 4. 操作权限分级

### 自动允许

- 进程、端口、健康接口和有限日志。
- Flink REST只读查询。
- Kafka list/describe。
- Doris/MySQL `SELECT`、`SHOW`、`DESCRIBE`。
- Redis `INFO`、`DBSIZE`和受限`SCAN`。
- 已审计脚本的`status`。

### 人工确认

- 启动或重启组件。
- 提交Flink Job。
- 构建和发布。
- 调整资源与并行度。

### 高风险审批

- 停止组件。
- `flink cancel`或`stop`。
- Savepoint恢复。
- 修改生产配置。
- 补数和回滚。

### 默认禁止

- `DELETE`、`DROP`、`TRUNCATE`和任意清理。
- 修改网络、主机名、SSH和安全组。
- 执行任意模型生成Shell。
- 读取或输出秘密。
- `Redis KEYS`全库扫描。
- 自动执行`init_data1.sh`。

## 5. 脚本审计要求

脚本进入白名单前必须记录：

- 参数。
- 目标节点。
- 调用的下级命令。
- 是否修改文件或数据。
- 是否检查重复进程/Job。
- 退出码与失败处理。
- 超时。
- 幂等性。
- 回滚条件。
- 是否打印秘密。

## 6. 只读查询约束

- 日志最多最近200行或30分钟。
- 大表不得无条件`COUNT(*)`。
- Redis使用小批量`SCAN`，禁止`KEYS`。
- HTTP健康检查单次调用，不压测。
- 命令设置超时，失败不无限重试。
- 不读取Shell History、私钥、`.env`内容或云Metadata。
- 配置、进程参数和日志中的秘密统一脱敏。

## 7. 缺失的运维能力

- 核心组件可靠开机自启。
- 进程异常自动恢复。
- 统一审计日志。
- 完整发布、版本和回滚流程。
- 经验证的Savepoint恢复演练。
- Kafka Consumer Group/Lag可靠观测。
- 自动化CI/CD。
- Prometheus/Grafana实际部署和Dashboard。
- Docker/Compose部署物。
