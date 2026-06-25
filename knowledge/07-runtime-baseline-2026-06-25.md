# 运行基线：2026-06-25

本文件记录2026-06-25的只读巡检结果，只用于历史对比，不代表当前状态。

## 1. 调查范围

- data1 `192.168.1.10`
- data2 `192.168.1.20`
- data3 `192.168.1.30`
- 调查方式：SSH、进程、端口、组件API和只读数据库查询
- 深度采样：约70秒，3轮，每轮间隔约35秒

70秒采样只能说明当时短时间内未恶化，不能证明长期稳定。

## 2. 主机状态

| 主机 | OS | CPU | 内存总量/当时可用 | 根磁盘 | 运行时间 |
|---|---|---:|---:|---:|---:|
| data1 | Ubuntu 22.04.5 LTS | 8核 | 29Gi / 约17Gi | 40G，使用55% | 约37分钟 |
| data2 | Ubuntu 22.04.5 LTS | 8核 | 14Gi / 约9.6Gi | 40G，使用52% | 约37分钟 |
| data3 | Ubuntu 22.04.5 LTS | 8核 | 14Gi / 约9.4Gi | 40G，使用51% | 约37分钟 |

- 三台未配置Swap。
- 未发现OOM。
- dmesg存在AliSecGuard内核模块警告。
- inode使用约9%。
- `ulimit -n`为65535。
- 系统时间同步正常。

## 3. 组件运行状态

| 组件 | 节点 | 当时状态 | PID快照 | 端口 |
|---|---|---|---:|---|
| MySQL | data1 | 运行 | 1411 | 3306、33060 |
| Redis | data1 | 运行 | 1048 | 6379 |
| Kafka | data1 | 运行 | 18700 | 9092 |
| Doris FE | data1 | 运行 | 17553 | 8030、9030 |
| Doris BE | data2 | 运行 | 15016 | 8040、9050、9060 |
| Doris BE | data3 | 运行 | 3786 | 8040、9050、9060 |
| Flink JM | data1 | 运行 | 16604 | 8081、6123 |
| Flink TM | data2 | 运行 | 2834 | 动态 |
| Flink TM | data3 | 运行 | 2950 | 动态 |
| Collector | data1 | 运行 | 15838 | 无 |
| Spring API | data1 | 运行 | 19284 | 8080 |
| AI Engine | data1 | 运行 | 19208 | 8000 |
| 前端 | data1 | 未部署 | — | — |
| Milvus | 未部署 | 未运行，符合本轮预期 | — | — |

PID仅用于定位当时证据，不得复用。

## 4. Flink状态

- 1个JobManager。
- 2个TaskManager。
- 每个TaskManager配置6个Slot，总计12个。
- TaskManager启动参数显示约4.5GiB最大Heap。

### Jobs

| Job | 状态 | 报告中的总SubTask数 | 单算子最大并行度线索 |
|---|---|---:|---:|
| `streamlake-kline-aggregation` | RUNNING | 15 | 3 |
| `streamlake-whale-cep` | RUNNING | 15 | 3 |
| `streamlake-risk-control` | RUNNING | 7 | 约2 |

Flink Slot Sharing允许同一Job不同算子的SubTask共享Slot，因此总SubTask数不等于实际所需Slot数。当时12个Slot足以承载三个Job。

### Checkpoint

- Kline和Whale观察到成功Checkpoint。
- Risk最近抽查ID 18～26均为`COMPLETED`。
- 耗时约200ms。
- 状态大小约180～330KB。
- 未观察到Checkpoint失败。
- 目标为`oss://streamlake-paimon-tokyo/flink-checkpoints/`。

## 5. Kafka状态

观察到Topic：

- `binance.depth.raw`
- `binance.trade.raw`
- `streamlake.whale.alert`

问题：

- `kafka-consumer-groups.sh --list`返回空。
- 代码存在`flink-kline-group`、`flink-cep-group`、`flink-risk-group`。
- Checkpoint正常，但Broker未观察到已提交Consumer Group Offset。
- 原因未查清，不能认定为正常。

## 6. Doris状态

数据库：

- `streamlake`
- `__internal_schema`

当时数据量：

| 表 | 行数/状态 |
|---|---:|
| `kline_1min` | 56,107 |
| `whale_alert` | 16,877 |
| `risk_trigger` | 65,783 |
| `ai_diagnosis` | 已创建 |

数据新鲜度：

- `kline_1min.max(open_time)`在采样期间从11:50推进到11:51。
- 相对物理时间延迟约20～60秒，符合1分钟窗口。
- `whale_alert`没有推进，当时解释为未触发事件，不能仅凭不增长判断故障。

重复抽样：

- `kline_1min`按业务键抽样未发现重复。
- `whale_alert`按`alert_id`未发现相同ID重复。
- `risk_trigger`按`trigger_id`未发现相同ID重复。
- 随机UUID可能掩盖业务事件重放，以上结果不能证明没有业务重复。

## 7. Redis与MySQL

### Redis

- 内存约1.33MiB。
- 使用受限`SCAN`发现多个`risk:blacklist:*` Key。
- 示例涉及TIAUSDT、DOTUSDT和TRXUSDT。
- Key存在TTL，证明当时Risk链路有写入。

### MySQL

- 数据库：`risk_control`
- `whale_thresholds`：7条。
- `risk_rules`：5条。

## 8. API与AI

- Spring `/actuator/health`返回`{"status":"UP"}`。
- `/api/kline/latest`可访问，数据时间随Doris推进。
- AI `/health`返回`{"status":"ok"}`。
- Milvus未启动时AI Engine正常降级。

## 9. 进程资源

当时RSS线索：

| 节点 | 组件 | RSS |
|---|---|---:|
| data1 | Doris FE | 约6.3GiB |
| data1 | Kafka | 约1GiB |
| data1 | Flink JM | 约859MiB |
| data2 | Flink TM | 约2GiB |
| data3 | Flink TM | 约1.5GiB |
| data2/data3 | Doris BE | 各约1.8GiB |
| data1 | Collector/AI | 报告称约26MiB量级 |

data1三轮采样可用内存约9.3GiB且未明显变化。

结论边界：

- 三节点短时间运行无明显内存争抢。
- 不能由此推出单台16GiB可运行全部组件。
- 当前物理拆分是内存余量充足的重要原因。

## 10. 网络与时间

- NTP同步正常。
- Crontab存在每小时`ntpdate -u ntp.aliyun.com`。
- 内网可达Kafka 9092、Doris 9030、Redis 6379。
- UFW未启用。
- 多个服务监听全局或内网地址。
- 云安全组规则未核实。

## 11. 当时暴露的运维风险

- 除MySQL和Redis外，多数组件不由systemd或容器重启策略托管。
- 服务器重启后，Kafka、Flink、Doris、Collector、API和AI可能需要手工恢复。
- Kafka Consumer Group/Offset不可见。
- 前端未部署。
- Paimon未发现实际数据库或写入链路。
