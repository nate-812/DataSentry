# Agent知识接入与查询规范

## 1. 目标

Agent不需要把整个项目装进模型上下文。它需要：

- 用主题文档获得稳定地图。
- 用现场工具获取动态状态。
- 用SQLite保存巡检和故障记录。
- 用权限层约束写操作。

第一版只读诊断即可，不需要向量数据库。

## 2. 启动加载

每个新会话先读取：

1. `knowledge/INDEX.md`
2. 本文档

不要默认加载其余全部文档。

根据用户问题，从索引中选择1～3份主题文档。

示例：

```text
“K线为什么不更新？”
→ 读取03-jobs-and-lineage
→ 读取04-configuration-and-reliability
→ 必要时读取02-deployment-map
```

## 3. 查询流程

```text
理解问题
→ 从INDEX选择主题知识
→ 构建相关组件链路
→ 选择白名单只读工具
→ 查询服务器实时状态
→ 对比稳定知识和历史基线
→ 保存结构化快照
→ 输出证据、结论、未知和建议
```

## 4. 问题类型路由

### 数据不更新

1. 读取任务与血缘。
2. 找到上游Source、Job、Sink和服务入口。
3. 从上游向下游逐段检查数据新鲜度。
4. 找到最后一个仍在推进的节点。

### 组件宕机

1. 读取部署地图。
2. 查进程、端口、健康接口和有限日志。
3. 读取运维手册。
4. 只提供已有依据的启动建议。
5. 未经确认不自动启动。

### 延迟/反压

1. 读取任务与可靠性文档。
2. 查Source吞吐、各Vertex忙碌度、反压、Checkpoint和Sink耗时。
3. 查Kafka最新Offset、Flink Source指标和Doris最新业务时间。

### 配置问题

1. 读取配置文档。
2. 查询环境变量名、配置文件和启动参数。
3. 按优先级确定生效值。
4. 脱敏。

### 历史相似故障

第一版从SQLite按组件、故障类型和时间查询，不使用向量库。

## 5. 工具白名单

建议将工具定义为固定函数，而不是任意Shell：

```text
get_host_status(host)
get_service_status(host, component)
get_flink_jobs()
get_flink_job(job_id)
get_flink_checkpoints(job_id)
get_flink_backpressure(job_id)
get_kafka_topics()
get_kafka_topic(topic)
get_kafka_group(group)
get_doris_table_freshness(table)
get_redis_key_sample(pattern, limit)
get_api_health(service)
get_recent_logs(component, minutes, limit)
```

执行器负责：

- 参数校验。
- 命令映射。
- 超时。
- 输出大小。
- 脱敏。
- 审计。

模型只能选择工具和填写有限参数。

## 6. 证据格式

每条诊断事实包含：

```json
{
  "claim": "Kline Job当前未运行",
  "status": "confirmed",
  "source": "flink_rest",
  "target": "data1:8081",
  "observed_at": "ISO-8601",
  "evidence": "jobs列表中无streamlake-kline-aggregation"
}
```

状态只能是：

- `confirmed`
- `inferred`
- `unknown`

历史文档中的内容必须标记为`historical`，不能包装成当前状态。

## 7. SQLite持久化

最小表结构：

### inspections

```text
id
started_at
finished_at
question
scope
status
summary
```

### observations

```text
id
inspection_id
component
metric_or_fact
value_json
observed_at
source
```

### findings

```text
id
inspection_id
severity
status
claim
evidence_json
recommendation
```

### incidents

```text
id
opened_at
closed_at
symptom
root_cause
actions_json
verification_json
```

### operations

```text
id
requested_at
approved_at
executed_at
operation
parameters_json
risk
result_json
```

## 8. 静态知识更新

当源码、部署或架构变化时：

1. 更新对应主题文档。
2. 更新`INDEX.md`路由。
3. 记录更新时间和证据。
4. 不把当前PID、数据量或临时日志写入主题文档。

历史运行状态进入SQLite，不覆盖稳定知识。

## 9. 操作控制

| 风险 | Agent行为 |
|---|---|
| 只读 | 自动执行并审计 |
| 低/中写操作 | 展示参数、影响、验证方式，等待确认 |
| 高风险 | 要求明确审批、回滚/恢复方案和操作后验证 |
| 破坏性 | 默认拒绝 |

每个允许的写操作必须具备：

- 前置条件。
- 影响范围。
- 幂等性判断。
- 恢复或回滚方案。
- 操作后验证。
- 超出预期自动停止。

## 10. 输出规范

Agent回答应按以下顺序：

1. 当前结论。
2. 已确认的证据。
3. 推断。
4. 未知项。
5. 建议下一步。
6. 若需写操作，单独列出审批请求。

示例：

```text
结论：K线链路停在Flink计算层。

已确认：
- Collector仍在向binance.trade.raw写入。
- Kline Job不在RUNNING列表。
- Doris最新open_time停在10分钟前。

推断：
- 服务器重启后Job未重新提交。

未知：
- Job上次退出原因，需读取最近JobManager日志。

建议：
- 先查有限日志；确认无重复Job后，再申请执行job.sh k。
```

## 11. 缺失组件提醒

若预期组件未运行：

```text
[需要用户处理]
组件：
当前状态：
证据：
影响：
建议操作：
操作后复查：
```

只有知识库或服务器中存在可靠启动依据时才能给出命令。否则写“启动方式未知”。

明确例外：

- Milvus未启动是当前允许状态。
- 前端未部署不属于后端主链路故障。

## 12. Token与速度控制

- 默认只读`INDEX + 当前问题相关主题文档`。
- 结构化工具先过滤、聚合日志和指标。
- 每次只取最近必要日志。
- 历史记录按组件、时间、故障类型查询。
- 会话过程压缩为结构化事件状态。
- 不重复加载历史报告。

## 13. 第一版开发边界

实现：

- 主题知识加载。
- 白名单只读查询。
- SQLite快照。
- 证据化诊断。
- 缺失组件提醒。

暂不实现：

- RAG。
- 自动重启。
- 自动补数。
- 自动改配置。
- 自动Savepoint恢复。
- 任意Shell。
