# 任务、Topic与数据血缘

## 1. 端到端主链路

```text
Binance WebSocket
→ Collector
→ Kafka binance.trade.raw
   ├→ KlineAggregationJob
   │  └→ Doris kline_1min
   ├→ WhaleCepJob
   │  ├→ Doris whale_alert
   │  └→ Kafka streamlake.whale.alert
   └→ RiskControlJob
      ├→ Doris risk_trigger
      └→ Redis risk:blacklist:{SYMBOL}

MySQL whale_thresholds → WhaleCepJob（启动时读取一次）
MySQL risk_rules → RiskControlJob（每30秒轮询）
```

`binance.depth.raw`已在Kafka观察到，但当前三大Flink Job对它的消费链路未在现有调查中确认。

## 2. Collector

| 属性 | 内容 |
|---|---|
| 入口 | `collector/main.py` |
| 输入 | Binance WebSocket行情 |
| 输出 | Kafka原始行情Topic |
| 主要Topic | `binance.trade.raw`、`binance.depth.raw` |
| 并发方式 | asyncio/websockets |
| 连接约束线索 | 每约200个Stream拆分连接 |
| 容错 | 指数退避自动重连 |
| 部署 | data1 `/opt/StreamLake-Binance/collector` |

## 3. KlineAggregationJob

| 属性 | 内容 |
|---|---|
| 入口 | `com.streamlake.kline.KlineAggregationJob.main` |
| Consumer Group | `flink-kline-group` |
| Source | Kafka `binance.trade.raw` |
| 反序列化 | `TradeEventDeserializer` |
| 清洗 | 过滤空字段 |
| 时间语义 | 事件时间 |
| Watermark | 最大乱序5秒 |
| 倾斜处理 | BTC/ETH高流量交易分流 |
| 窗口 | 1分钟滚动事件时间窗口 |
| Trigger | 每5秒Processing Time中间触发，Watermark越界最终触发 |
| Sink | 自定义`DorisJdbcUpsertSink` |
| 输出 | Doris `kline_1min` |

诊断K线不更新时，按以下顺序检查：

```text
Collector进程与日志
→ binance.trade.raw是否有新数据
→ Kline Job是否RUNNING
→ Source/Window/Sink Vertex状态
→ Checkpoint与反压
→ Doris kline_1min最新open_time
→ API /api/kline/latest
```

## 4. WhaleCepJob

| 属性 | 内容 |
|---|---|
| 入口 | `com.streamlake.cep.WhaleCepJob.main` |
| Consumer Group | `flink-cep-group` |
| Source | Kafka `binance.trade.raw` |
| 时间语义 | 事件时间 |
| Watermark | 最大乱序5秒，空闲检测10秒 |
| 规则来源 | MySQL `whale_thresholds` |
| 更新方式 | Job启动时读取一次，不热更新 |
| CEP | 60秒内至少3次超过阈值的交易，贪婪匹配 |
| 输出1 | Doris `whale_alert` |
| 输出2 | Kafka `streamlake.whale.alert` |
| 脏数据 | `flatMap`中静默丢弃无法解析数据 |
| Offset起点 | 代码配置`auto.offset.reset=latest` |

重要边界：

- 没有巨鲸告警不一定是故障，事件可能暂未触发。
- 应同时检查Source吞吐、阈值加载日志和CEP算子状态。
- 阈值表更新后，现有Job不会自动加载新阈值，需重启才会生效。

## 5. RiskControlJob

| 属性 | 内容 |
|---|---|
| 入口 | `com.streamlake.risk.RiskControlJob.main` |
| Consumer Group | `flink-risk-group` |
| Source | Kafka `binance.trade.raw` |
| 时间语义 | `WatermarkStrategy.noWatermarks()`，处理时间 |
| 规则来源 | MySQL `risk_rules` |
| 更新方式 | `MySqlRulesSource`每30秒轮询 |
| 状态 | Broadcast State |
| 数据分发 | 交易流`rebalance()`后连接广播规则 |
| 输出1 | Doris `risk_trigger` |
| 输出2 | Redis `risk:blacklist:{SYMBOL}` |
| Redis TTL | 86400秒/24小时 |

Redis黑名单按交易对`SYMBOL`组织，不是账户级黑名单。

## 6. Topic血缘

| 上游Topic | Consumer Group | 任务 | 下游 |
|---|---|---|---|
| `binance.trade.raw` | `flink-kline-group` | KlineAggregationJob | Doris `kline_1min` |
| `binance.trade.raw` | `flink-cep-group` | WhaleCepJob | Doris `whale_alert`、Kafka `streamlake.whale.alert` |
| `binance.trade.raw` | `flink-risk-group` | RiskControlJob | Doris `risk_trigger`、Redis黑名单 |
| `binance.depth.raw` | 未确认 | 未确认 | 未确认 |

## 7. 表与Key血缘

| 上游 | 处理者 | 下游 |
|---|---|---|
| Binance Trade | Collector/Kafka/Kline Job | Doris `kline_1min` |
| MySQL `whale_thresholds` + Binance Trade | WhaleCepJob | Doris `whale_alert` |
| MySQL `whale_thresholds` + Binance Trade | WhaleCepJob | Kafka `streamlake.whale.alert` |
| MySQL `risk_rules` + Binance Trade | RiskControlJob | Doris `risk_trigger` |
| MySQL `risk_rules` + Binance Trade | RiskControlJob | Redis `risk:blacklist:{SYMBOL}` |
| AI分析结果 | AI/API链路 | Doris `ai_diagnosis`，具体写入路径尚未完全确认 |
| Doris `whale_alert` | `index_builder.py` | Milvus `whale_alert_cases` |

## 8. 无法闭合的链路

- `paimon_oss.ods.trade_raw`的写入方未在Flink/Kafka代码中找到。
- Doris `ai_diagnosis`已建表，但完整写入调用链证据不足。
- `binance.depth.raw`的生产已观察到，消费方未确认。
- 前端没有运行态，无法闭合API到用户页面的链路。

## 9. 重复与一致性风险

- `kline_1min`使用UNIQUE KEY，相同业务键可被覆盖。
- Whale/Risk事件使用随机UUID写DUPLICATE KEY表。
- 故障恢复时，相同业务事件可能生成新UUID并重复落库。
- 2026-06-25按`alert_id`和`trigger_id`抽样未发现相同ID重复，只能证明相同UUID未重复，不能排除同一业务事件被赋予新UUID。
