# Kafka Timeout 排查 Playbook

本文档用于 M9-R2：`get_kafka_topic` 对 `data1` 返回 `tool.timeout` 的后续排查。它只描述下次 `data1` 打开后的只读复查顺序；不开云端实例时不执行 SSH、不访问生产端口、不重启 Kafka、不修改 broker 配置、不删除 topic、不执行生产写操作。

## 适用范围

- DataSentry 真实只读巡检中只有 Kafka Topic 工具 timeout，但 Flink Job、Doris freshness、Spring API 等替代证据仍能证明 K 线主链路推进。
- 需要确认 timeout 是 broker 响应慢、Kafka CLI 环境限制、只读账号 PATH、网络抖动，还是 Consumer Group coordinator 相关问题。
- 不用于处理 Kafka 数据修复、Topic 删除、broker 重启、保留策略修改或 Consumer Group offset 修改。

## 候选原因

| 原因 | 迹象 | 本地准备 |
|---|---|---|
| broker 响应慢 | Topic describe/list 偶发超时，复跑可能成功 | 记录命令耗时、超时阈值和是否连续复现 |
| Kafka CLI 环境限制 | 固定 SSH 命令能登录，但找不到 Kafka CLI 或依赖环境 | 只记录 PATH、脚本路径和退出码，不修改环境 |
| 只读账号 PATH | root 能执行，`datasentry-readonly` 找不到命令或权限不足 | 记录账号、命令路径和脱敏 stderr |
| 网络抖动 | 同一命令间歇成功，host/Flink/Spring 证据正常 | 连续复查 2 到 3 次，记录每次耗时 |
| Consumer Group coordinator | Topic 工具成功但 group 查询超时或 `FIND_COORDINATOR` 失败 | 区分 Topic 元数据和 Consumer Group 状态，不把 group timeout 等同于主链路中断 |

## 只读复查顺序

1. 记录维护窗口、云端 Git commit、目标主机和当前 DataSentry 配置路径。
2. 运行 `datasentry ops preflight --targets-file /etc/datasentry/targets.toml`，确认只读目标和 secret 状态只显示 configured/missing。
3. 复跑固定 Kafka Topic 只读工具，记录命令耗时、退出码和脱敏 stderr。
4. 若 Topic 工具 timeout，复查固定 host、Flink Job、Doris freshness 和 Spring API 固定读探针，确认是否仍有替代证据证明主链路推进。
5. 若 Topic 工具成功，再复查 Consumer Group 工具；group timeout 只记录为 group 层风险，不直接推断 Topic 或主链路中断。
6. 将结果写入 `docs/operations/maintenance-evidence-record.md` 格式的维护记录，并更新 M9-R2 状态。

## 判定矩阵

| 结果 | 判定 | 下一步 |
|---|---|---|
| Topic 工具连续成功 | M9-R2 可关闭或降为观察 | 记录成功耗时和 Inspection id |
| Topic 偶发 timeout，但替代证据正常 | Kafka CLI 或网络层不稳定 | 保留风险，优化超时阈值或记录降级说明 |
| Topic 连续 timeout，Flink/Doris/Spring 正常 | Kafka 元数据工具不可用但主链路可由替代证据确认 | 记录工具限制，不把主链路判定为中断 |
| Topic timeout 且 Flink/Doris/Spring 异常 | 可能存在真实链路风险 | 停止收口动作，升级到维护窗口排障 |
| Group 查询 timeout，Topic 正常 | Consumer Group coordinator 或 group 状态问题 | 单独记录 group 风险，不扩大为 Topic 风险 |

## 降级证据

当 `get_kafka_topic` 仍为 timeout 时，允许用以下只读证据组合支撑“K 线主链路当前正在推进”的降级判断：

- Flink Job 为 RUNNING，checkpoint 连续失败数为 0，backpressure 为 ok。
- Doris `kline_1min` freshness 在可接受窗口内。
- Spring API K 线固定读探针返回 ok。
- Collector 进程或服务状态正常。
- 命令耗时、退出码和脱敏 stderr 已记录，且未打印真实 secret。

降级证据只能说明本次巡检的诊断依据，不代表 Kafka timeout 已关闭。

## 关闭条件

M9-R2 可以关闭的条件：

- 固定 Kafka Topic 工具在维护窗口内稳定 succeeded，记录命令耗时、退出码和 Inspection id。
- 或已确认 timeout 只影响 Kafka CLI/账号环境，且 DataSentry 诊断规则有明确替代证据说明，不再误判主链路。
- 状态文档和风险 backlog 已记录当前结论、未验证项和下一次复查条件。
