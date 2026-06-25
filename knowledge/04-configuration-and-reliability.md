# 配置、状态与可靠性

## 1. 配置来源与优先级

项目中观察到的通用优先级：

1. 环境变量。
2. 本地配置文件。
3. 代码硬编码默认值。

具体情况：

- Flink Jobs通过自定义`env("VAR_NAME", "default")`优先读环境变量。
- Spring Boot使用`${ENV:default}`形式。
- Python服务使用`os.getenv`。
- Collector主要使用`collector/config.yaml`。
- 部分Java默认值中存在硬编码地址和凭据风险。

Agent读取配置时必须：

- 只返回配置键、来源和脱敏值。
- 不读取或输出密码、Token、AK/SK和私钥。
- 记录最终生效来源，而不只看仓库默认值。
- 现场确认环境变量、启动参数和配置文件的覆盖关系。

## 2. 已知配置线索

| 配置 | 已知线索 | 当前性质 |
|---|---|---|
| Kafka bootstrap | `192.168.1.10:9092` | 代码/配置默认及服务器地址 |
| Doris连接 | data1 `9030` | 服务器确认 |
| Redis | data1 `6379` | 服务器确认 |
| MySQL | data1 `3306` | 服务器确认 |
| Flink Web | data1 `8081` | 服务器确认 |
| OSS Checkpoint | `oss://streamlake-paimon-tokyo/flink-checkpoints/` | 配置与运行观察 |
| Kafka保留 | 6小时或3GB上限 | 项目资料，服务器实际值仍需确认 |
| Redis黑名单TTL | 86400秒 | 代码/资料 |

Spring配置中出现`initialization-fail-timeout: -1`。它表示连接池初始化时不立即因连接失败而终止；实际影响需结合数据源类型和启动日志判断，不能直接等同于系统健康。

## 3. Flink Checkpoint与状态

### KlineAggregationJob

- 代码未显式调用`enableCheckpointing`。
- 2026-06-25服务器观察到其Checkpoint成功。
- 实际行为依赖集群或提交配置，不能只根据代码判断。

### WhaleCepJob

- 代码显式`env.enableCheckpointing(30_000)`。
- 使用CEP状态。
- 2026-06-25观察到Checkpoint成功。

### RiskControlJob

- 代码显式`env.enableCheckpointing(30_000)`。
- MySQL规则写入Broadcast State。
- 2026-06-25最近抽查的Checkpoint全部完成。

### 状态后端

早期资料称使用RocksDB，服务器完整生效配置尚未形成可靠证据。Agent应现场读取Flink配置和REST API，不得只凭规划文档确认。

## 4. 时间语义与乱序

| Job | 时间语义 | Watermark/窗口 |
|---|---|---|
| Kline | 事件时间 | 5秒乱序，1分钟滚动窗口 |
| Whale | 事件时间 | 5秒乱序，10秒空闲检测，60秒CEP |
| Risk | 处理时间 | 无Watermark、无事件时间窗口 |

时钟异常会影响窗口、Watermark和告警。巡检应检查：

- `timedatectl`
- NTP/chrony状态
- 节点间时间差
- 业务事件时间是否落后或超前

2026-06-25三节点系统时间同步正常，并存在每小时调用`ntpdate -u ntp.aliyun.com`的Crontab。

## 5. Source恢复与Kafka Offset

- KafkaSource的读取位置可保存在Flink Checkpoint中。
- 代码配置了三个`group.id`。
- 2026-06-25使用`kafka-consumer-groups.sh --list`查询不到Consumer Group。
- 该现象不能直接判定为正常。
- 需要进一步确认：
  - `commit.offsets.on.checkpoint`
  - KafkaSource实际属性
  - Broker `__consumer_offsets`
  - 查询权限和bootstrap地址
  - Checkpoint完成后是否提交监控Offset

在问题解决前，Agent不能依赖Kafka Broker已提交Offset计算Lag，应结合Flink Source指标和Kafka最新Offset判断。

## 6. Sink与数据语义

### Kline Doris Sink

- 自定义JDBC批量Upsert。
- Doris `kline_1min`使用UNIQUE KEY。
- 相同业务键可被覆盖。
- 不能只凭UNIQUE KEY和Checkpoint宣称端到端Exactly-Once。

### Whale/Risk Doris Sink

- 事件使用随机UUID。
- Doris表使用DUPLICATE KEY。
- 故障重放可能为同一业务事件生成不同UUID。
- 需要业务唯一键或去重策略才能确认端到端重复控制。

### Redis Sink

- Risk Job使用`setex`写入24小时TTL。
- 相同`SYMBOL`覆盖当前黑名单状态，适合保存最新状态。

### Kafka Whale Sink

- Whale Job写`streamlake.whale.alert`。
- 事务和交付语义未在现有资料中完整确认。

## 7. 重启、恢复与重放

已确认：

- Collector有WebSocket指数退避重连。
- Flink Checkpoint写OSS。
- MySQL、Redis由systemd托管。

未确认或缺失：

- Flink集群级重启策略是FixedDelay还是Exponential Backoff。
- Kafka、Flink、Doris和多数业务服务没有可靠自动拉起。
- Savepoint创建、版本升级和恢复流程未被验证。
- Kafka仅短时保留时，长时间停机可能超出可重放范围。
- 补数工具无自动回滚。

## 8. 数据保留与清理

- 项目资料称Kafka日志保留6小时或3GB上限。
- Redis黑名单TTL 24小时。
- Doris表保留和分区清理策略未完整确认。
- Paimon/OSS数据保留策略未确认。
- Agent不得根据资料自动执行清理，应现场读取实际配置。

Kafka资料还记录了Binance每连接约200个Stream的订阅限制，Collector通过拆分连接适配；该限制变化时应以Binance当前规则为准。

## 9. 可靠性检查清单

一次只读可靠性巡检至少检查：

1. 三个Job是否RUNNING。
2. 最近Checkpoint成功时间、耗时、大小和连续失败数。
3. TaskManager、Slot和Vertex状态。
4. Source输入是否推进。
5. Doris最新业务时间是否推进。
6. Redis Key TTL是否合理。
7. OSS Checkpoint目录最近写入时间。
8. OOM、GC长暂停、磁盘和inode。
9. Kafka保留是否覆盖最大恢复时间。
10. 是否存在服务器重启后无法自动恢复的组件。
