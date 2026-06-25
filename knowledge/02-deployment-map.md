# 部署与组件地图

## 1. 节点清单

| 节点 | 地址 | CPU/内存快照 | 稳定职责 |
|---|---|---|---|
| data1 | `192.168.1.10` | 8核、29Gi | 主控、消息、规则、API与AI |
| data2 | `192.168.1.20` | 8核、14Gi | Flink计算、Doris存储 |
| data3 | `192.168.1.30` | 8核、14Gi | Flink计算、Doris存储 |

CPU和内存数值来自2026-06-25快照；机器规格变化时应更新。

## 2. 组件位置

| 组件 | 节点 | 程序/源码路径 | 进程指纹 | 端口 | 路径可信度 |
|---|---|---|---|---|---|
| Kafka | data1 | `/opt/kafka` | `java (kafka.Kafka)` | 9092 | 已确认 |
| Flink JobManager | data1 | `/opt/flink` | `StandaloneSessionClusterEntrypoint` | 8081、6123 | 已确认 |
| Flink TaskManager | data2、data3 | `/opt/flink` | `TaskManagerRunner` | 动态 | 已确认 |
| Doris FE | data1 | 精确程序路径待确认 | Java Doris FE | 8030、9030 | 组件与端口已确认，路径未知 |
| Doris BE | data2、data3 | 精确程序路径待确认 | `doris_be` | 8040、9050、9060 | 组件与端口已确认，路径未知 |
| MySQL | data1 | 系统安装 | `mysqld` | 3306、33060 | 已确认 |
| Redis | data1 | 系统安装 | `redis-server` | 6379 | 已确认 |
| Collector | data1 | `/opt/StreamLake-Binance/collector` | `python main.py` | 无监听端口 | 已确认 |
| Spring API | data1 | `/opt/StreamLake-Binance/api-server` | `java -jar` | 8080 | 已确认 |
| AI Engine | data1 | `/opt/StreamLake-Binance/ai-engine` | `uvicorn main:app` | 8000 | 已确认 |
| 项目源码 | data1 | `/opt/StreamLake-Binance` | — | — | 已确认 |
| 运维脚本 | data1 | `/root/bin` | Shell脚本 | — | 已确认 |
| 前端 | data1 | `/opt/StreamLake-Binance/frontend` | 无进程 | 无 | 仅源码目录 |
| Milvus | 未部署 | 位置待定 | 无进程 | 19530为规划端口 | 代码规划 |

## 3. 必须区分的路径

Agent不能把“安装目录”当成所有操作的路径。每个组件至少有：

- 程序或JAR路径。
- 配置路径。
- 日志路径。
- 数据或状态路径。
- PID文件或进程托管位置。

当前已知稳定程序路径有限。Doris、Kafka、Flink等组件的配置、日志和数据目录应在执行操作前现场查询。

## 4. 网络与外部依赖

| 连接 | 方向 | 用途 |
|---|---|---|
| Binance WSS `wss://stream.binance.com:9443` | 外部 → Collector | 实时行情 |
| Collector → `192.168.1.10:9092` | data1内部 | Kafka写入 |
| Flink TM → Kafka | data2/data3 → data1 | 行情消费 |
| Flink TM → MySQL | data2/data3 → data1 | 阈值和规则读取 |
| Flink TM → Redis | data2/data3 → data1 | 黑名单写入 |
| Flink/Doris客户端 → Doris FE `9030` | 集群内部 | JDBC/MySQL协议写入与查询 |
| Flink → 阿里云OSS | 集群 → 云存储 | Checkpoint |
| API → Doris/Redis/AI | data1内部 | 查询与诊断 |

2026-06-25巡检发现Kafka、Doris FE、Flink Web、API和AI等端口绑定全局地址或内网地址，且UFW未启用。公网隔离依赖云安全组，必须现场确认。

OSS资料中的内网Endpoint为`oss-ap-northeast-1-internal.aliyuncs.com`，实际生效Endpoint应脱敏读取配置后确认。

## 5. 运行托管方式

### systemd托管

- MySQL
- Redis

### 手工脚本或nohup

- Kafka
- Flink集群
- Flink Jobs
- Doris FE/BE
- Collector
- Spring API
- AI Engine

这些组件在服务器重启或进程异常退出后可能无法自动恢复。`/root/bin`提供便捷脚本，但不等同于可靠的进程守护。

项目资料提到ENI固定IP和抢占式实例被释放后的恢复流程；服务器只确认了当前三个内网IP，未验证ENI绑定和抢占恢复机制。

## 6. 前端与Milvus

### 前端

服务器核查结果：

- 未安装Nginx。
- `/opt/StreamLake-Binance/frontend`未发现`dist`构建产物。
- 未发现Vite或Node前端进程。
- 不应提示用户启动Nginx。
- 是否需要部署前端尚未确定。

### Milvus

- 代码中存在Milvus客户端和Collection定义。
- 服务器未启动Milvus是已知且允许的状态。
- AI Engine在Milvus不可用时降级运行。
- 运维Agent不应要求启动Milvus，除非用户明确将业务案例检索纳入范围。

## 7. 规划中的监控端口

| 组件 | 规划端口 | 当前状态 |
|---|---:|---|
| Prometheus | 9090 | 未确认运行 |
| Grafana | 3000 | 未确认运行 |

项目资料提到这两个组件，但没有发现Dashboard、告警配置或服务器运行证据。

## 8. 动态字段

下列信息禁止固化为当前事实：

- PID。
- 当前内存和CPU。
- 当前Job状态。
- 当前数据行数。
- 当前JAR版本。
- 当前监听地址和安全组。
- 当前日志位置。

它们只能作为带时间戳的运行快照保存。
