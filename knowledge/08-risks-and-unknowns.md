# 风险、冲突与未知项

## 1. P0风险

### 1.1 网络暴露

已观察到Kafka、Doris FE、Flink Web、API和AI等端口绑定全局地址或内网地址，主机UFW未启用。

影响：

- 若云安全组开放，Kafka、Doris、Flink等管理面可能暴露公网。

待验证：

- 阿里云/AWS安全组入站规则。
- 是否仅允许管理IP和内网CIDR。

### 1.2 硬编码凭据

代码和SQL资料存在硬编码凭据默认值或AK/SK占位/明文风险。

要求：

- 不把任何秘密写入Agent知识库。
- 轮换已暴露或可能提交过的凭据。
- 使用环境变量或秘密管理。
- 日志和命令参数脱敏。

## 2. P1风险

### 2.1 缺少自动恢复

除MySQL、Redis外，Kafka、Flink、Doris、Collector、API和AI主要由脚本/nohup启动。

影响：

- 主机重启后链路不会自动恢复。
- OOM或进程异常退出后可能长期停机。
- 依赖人工按顺序恢复。

### 2.2 Kafka Consumer Group不可见

现象：

- 三个Job配置了Group ID。
- Flink Checkpoint成功。
- Kafka查询不到Consumer Group。

影响：

- 无法直接用Broker已提交Offset计算Lag。
- 故障恢复和监控行为不透明。

待查：

- `commit.offsets.on.checkpoint`
- Source属性
- Broker Offset数据
- 查询权限与命令

### 2.3 业务事件重复

- Whale/Risk事件使用随机UUID。
- Doris使用DUPLICATE KEY。
- Failover重放可能为同一业务事件生成新ID。
- 按ID查重无法识别这种重复。

需要：

- 定义业务唯一键。
- 设计幂等或去重策略。
- 做受控故障恢复测试。

### 2.4 运维脚本未审计

`/root/bin`存在便捷脚本，但未逐行确认：

- 副作用。
- 幂等性。
- 失败处理。
- 重复Job保护。
- 秘密输出。
- 跨节点SSH行为。

在完成审计前，只有`status`和受限日志查询可作为候选自动工具。

### 2.5 Kafka保留时间较短

资料称Kafka保留6小时或3GB。

影响：

- 故障超过保留窗口可能无法从Kafka重放。

服务器实际配置尚未确认。

## 3. P2风险与缺口

### Paimon

- SQL和OSS中有Paimon设计线索。
- 未发现`paimon_oss.ods.trade_raw`写入Job。
- Doris中未发现对应数据库。
- 当前更像未落地规划。

### 前端

- React/Vite源码存在。
- 云端没有构建产物、进程或Nginx。
- 是否需要前端未确定。
- 不应把未部署前端视为后端主链路故障。

### Milvus

- 业务案例检索代码存在。
- 服务器未运行Milvus。
- AI可降级。
- 对运维Agent不是必需依赖。

### 可观测性

资料提到Prometheus/Grafana，但未发现Dashboard或稳定告警通道。

缺口：

- 统一指标。
- 告警路由。
- 审计。
- 长期趋势。
- 数据质量告警。

### Spring数据源启动行为

配置中的`initialization-fail-timeout: -1`允许数据源连接失败时继续启动。它可能让服务进程存活但数据库能力不可用，应同时检查健康接口、连接池日志和真实查询。

## 4. 事实冲突与纠正记录

| 早期说法 | 整理后的结论 |
|---|---|
| Nginx未启动，需要启动 | 服务器未安装Nginx，前端未部署；无需启动 |
| Whale阈值动态更新 | 仅Job启动时加载一次 |
| 三个Job都已在代码开启Checkpoint | Kline未显式开启，运行时依赖集群配置 |
| Flink Offset不提交Kafka是完全正常 | Consumer Group为空原因未知，不能直接判正常 |
| Checkpoint + Doris等于Exactly-Once | Source恢复和各Sink语义必须分别判断 |
| `flink cancel`是回滚 | cancel/stop不是回滚；恢复需要有效Savepoint和验证流程 |
| 补数脚本风险低 | 无回滚，属于高风险 |
| 16GiB足以运行全部组件 | 只验证了三节点短时运行，不能推断单机规格 |
| Redis黑名单是账户黑名单 | Key按`SYMBOL`组织 |
| Flink直接向Doris BE写入 | 客户端通常通过Doris FE/JDBC入口；实际连接参数需确认 |

## 5. 尚未确认的技术事实

- Doris FE/BE精确程序、配置、日志和数据目录。
- Flink状态后端实际生效配置。
- Flink集群重启策略。
- Kafka Group Offset不可见原因。
- Kafka真实保留策略。
- Doris Compaction、导入失败和磁盘策略。
- OSS Checkpoint保留和清理策略。
- `ai_diagnosis`完整写入链路。
- `binance.depth.raw`消费方。
- Paimon是否保留或删除。
- 前端是否属于第一期范围。
- 云安全组规则。
- `/root/bin/*.sh`实际源码行为。

## 6. 不应阻塞第一版Agent开发的未知项

以下可以在运行时按需查询，不必先继续人工探索：

- 精确日志路径。
- 当前PID和JAR。
- 当前组件配置。
- 当前任务状态和指标。
- 当前Doris数据量。
- 当前安全组状态（若Agent暂不操作网络）。

## 7. 必须阻止自动操作的未知项

在确认前不得自动执行：

- 任意`start/stop/restart`脚本。
- `job.sh`。
- Savepoint恢复。
- 补数。
- 网络初始化。
- 数据删除和清理。
