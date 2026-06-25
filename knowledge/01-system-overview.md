# 系统总览

## 1. 项目定义

StreamLake-Binance 是一套全球加密货币实时行情、量化指标和风控系统。它从 Binance WebSocket/API采集行情，经Kafka缓冲，由Flink执行K线聚合、巨鲸行为识别和动态风控，再写入Doris、Redis和告警Topic，由Spring Boot API、AI Engine和React前端消费。

```text
Binance
→ Python Collector
→ Kafka
→ Flink
   ├→ Doris：K线、巨鲸告警、风控事件、AI诊断记录
   ├→ Redis：当前风控黑名单
   └→ Kafka：巨鲸告警
→ Spring Boot API / AI Engine / 前端
```

Flink Checkpoint写入阿里云OSS。MySQL保存巨鲸阈值和风控规则。

## 2. 技术栈

以下版本来自代码、配置或项目资料；实际运行版本在操作前仍应现场确认。

| 类别 | 技术/版本 | 用途 | 证据性质 |
|---|---|---|---|
| 操作系统 | Ubuntu 22.04.5 LTS | 云服务器底座 | 服务器已确认 |
| 数据采集 | Python 3.12、asyncio、websockets | Binance实时行情采集 | 代码/资料 |
| 消息队列 | Apache Kafka 3.8，KRaft | 原始行情与告警消息总线 | 资料与服务器 |
| 实时计算 | Apache Flink 2.0、JDK 21 | K线、CEP、风控 | 依赖与服务器 |
| OLAP | Apache Doris 3.0 | 指标、告警和诊断存储 | SQL与服务器 |
| 数据湖 | Apache Paimon 1.1 | 规划中的ODS/OSS数据湖 | 仅发现设计线索，未确认投入使用 |
| 缓存 | Redis 7.2 | 风控黑名单 | 资料与服务器 |
| 规则库 | MySQL | 巨鲸阈值、动态风控规则 | 代码与服务器 |
| API | Spring Boot 3.3、Virtual Threads | REST、WebSocket和查询服务 | 配置与代码 |
| AI服务 | FastAPI/Uvicorn | AI诊断接口 | 代码与服务器 |
| 向量库 | Milvus 2.4 | 巨鲸案例特征检索 | 代码存在，服务器未启动 |
| 前端 | React 19、Vite | 数据大屏 | 依赖存在，服务器未部署 |

项目资料还规划了Prometheus和Grafana，但服务器调查未确认其实际运行，也未发现Dashboard文件或完整告警通道。

## 3. 项目模块

| 模块 | 职责 | 关键入口 | 生产参与情况 |
|---|---|---|---|
| `collector/` | Binance WebSocket采集并写Kafka | `main.py` | 已运行 |
| `stream-jobs/job-kline` | 1分钟K线聚合 | `KlineAggregationJob.main` | 已运行 |
| `stream-jobs/job-whale-cep` | 巨鲸交易CEP检测 | `WhaleCepJob.main` | 已运行 |
| `stream-jobs/job-risk-control` | 动态规则风控 | `RiskControlJob.main` | 已运行 |
| `api-server/` | REST、WebSocket和实时推送 | `StreamLakeApplication` | 已运行 |
| `ai-engine/` | AI诊断与巨鲸案例检索 | `main.py` | 已运行，Milvus降级 |
| `frontend/` | React/Vite可视化大屏 | Vite入口 | 源码存在，云端未发现构建产物或进程 |
| `scripts/` | 补数及辅助脚本 | `backfill_klines.py` | 高风险辅助工具 |

## 4. 三层系统结构

### 数据与协调节点 data1

负责采集、消息总线、调度、规则、查询和应用服务：

- Kafka
- Flink JobManager
- Doris FE
- MySQL
- Redis
- Collector
- Spring API
- AI Engine

### 计算与存储节点 data2、data3

两台节点结构一致：

- Flink TaskManager
- Doris BE

### 外部依赖

- Binance WebSocket/API
- 阿里云OSS Bucket `streamlake-paimon-tokyo`
- 云安全组和内网

## 5. 已实现、规划和缺失边界

### 已实现并在2026-06-25观察到运行

- Collector → Kafka → 三个Flink Job。
- K线、巨鲸告警、风控事件写Doris。
- 风控黑名单写Redis。
- Spring API和AI Engine健康接口。
- Flink Checkpoint写OSS。

Collector资料描述订阅Top-50交易对，并按Binance每连接约200个Stream的限制拆分WebSocket连接；当前实际订阅数量需运行时查询。

### 代码存在但未完整启用

- AI Engine的Milvus巨鲸案例检索：Milvus未启动，服务降级运行。
- React前端：源码存在，服务器未发现`dist`、Vite/Node进程或Nginx。

### 仅规划或尚未确认

- Paimon ODS `paimon_oss.ods.trade_raw`的实际写入链路。
- Nginx不是当前已安装组件，不能视为必须启动的服务。
- 自动化CI/CD、完整发布和回滚流程未发现。
- Docker/Milvus在规划资料中出现，但仓库和服务器未发现可确认的Dockerfile或Compose部署物。
