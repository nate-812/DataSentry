# `/root/bin` 运维脚本审计结论

本文档基于用户提供的 `/Users/nate/Downloads/DataSentry/root_bin_audit_report.md` 做源码快照审计。审计对象是 2026-06-30 云端实例 `data1:/root/bin` 脚本详情，不代表当前云端实时状态；下次打开 `data1` 后仍需只读复核文件清单、权限、哈希和实际内容。

## 审计范围

已审计脚本：

- `init_data1.sh`
- `job.sh`
- `job.sh.bak-20260630-password-rotation`
- `kafka.sh`
- `spring.sh`
- `ai.sh`
- `doris.sh`
- `flink.sh`
- `xcall`
- `xsync`

## 总体结论

`/root/bin` 当前不满足 DataSentry 自动化准入要求。这批脚本可以作为人工维护窗口参考，但不得进入 DataSentry 自动执行白名单，也不得作为生产写 Runbook 的执行器来源。

主要原因：

- 多个脚本依赖 root 无密 SSH，扩大横向移动和误操作半径。
- `spring.sh` 与 `ai.sh` 以 root 权限运行应用，应用漏洞会直接放大为系统级风险。
- `job.sh` 缺乏幂等性，重复执行会重复提交 Flink Job。
- `spring.sh` 包含现场编译逻辑，不符合生产发布应使用已验证构建产物的边界。
- `ai.sh` 使用 `0.0.0.0:8000` 启动 AI Engine，和 M9 暴露面收口目标冲突。
- secret 依赖 `/root/.streamlake-secrets` 或外部环境变量注入，脚本自身没有脱敏输出、最小权限和泄漏保护。

## 高风险阻断项

| 阻断项 | 涉及脚本 | 影响 | 结论 |
|---|---|---|---|
| root 无密 SSH | `doris.sh`、`flink.sh`、`xcall`、`xsync` | 任一节点或脚本误用都可能横向影响 `data1`、`data2`、`data3` | 禁止自动执行；只能在人工维护窗口按只读优先原则复核 |
| root 权限运行应用 | `spring.sh`、`ai.sh` | API 或 AI Engine 漏洞会获得 root 权限 | 迁移到专用服务用户和 systemd 前不得自动化 |
| 缺乏幂等性 | `job.sh` | 可能重复提交同名 Flink Job，造成资源浪费、并发冲突或数据重复处理 | 需要先增加运行中 Job 检查和拒绝重复提交 |
| 现场编译 | `spring.sh` | 生产环境可能编译未验证代码，难以回滚和审计 | 应改为部署明确 Git commit 和预构建产物 |
| 公网监听倾向 | `ai.sh` | `0.0.0.0:8000` 与“不直接暴露 AI Engine”目标冲突 | 改为 loopback、内网或受控代理前不得作为生产模板 |
| secret 边界不完整 | `job.sh`、`spring.sh`、`ai.sh` | 依赖 `/root/.streamlake-secrets` 或环境变量，缺少统一脱敏和最小权限约束 | 保持人工注入和只读验证，不接自动执行 |

## 脚本逐项结论

| 脚本 | 风险等级 | 审计结论 | 自动化准入 |
|---|---|---|---|
| `init_data1.sh` | 中 | 会修改 hostname、netplan 和 root known_hosts，属于初始化写操作；硬编码 `192.168.1.x` 和主机名 | 禁止自动执行；仅限一次性初始化窗口 |
| `job.sh` | 中 | 会读取 `/root/.streamlake-secrets` 并提交 Flink Job，但没有检查同名 Job 是否已运行 | 禁止自动执行；补幂等检查前不接 Runbook |
| `job.sh.bak-20260630-password-rotation` | 中 | 旧备份脚本缺少 secret 加载逻辑，长期保留会造成混乱 | 应删除或移出运行目录；不得执行 |
| `kafka.sh` | 低到中 | 有基本状态检查和优雅停止等待；仍是 root 下启停脚本 | 不进入自动白名单；可作为人工维护参考 |
| `spring.sh` | 中 | root 运行 Java 服务，缺省 Doris 用户为 `root`，包含现场编译 | 迁移到专用用户、systemd、预构建产物前禁止自动执行 |
| `ai.sh` | 中到高 | root 运行 uvicorn，监听 `0.0.0.0:8000`，依赖外部 secret 环境 | 改为 loopback 和专用用户前禁止自动执行 |
| `doris.sh` | 高 | 跨节点 root SSH 启停 Doris FE/BE | 禁止自动执行；Doris root 改密窗口需单独处理 |
| `flink.sh` | 高 | 依赖 Flink 集群脚本和跨节点 root SSH | 禁止自动执行；保留人工维护窗口使用 |
| `xcall` | 高 | 可向三台主机分发任意 shell 命令，缺少失败一致性处理 | 永不进入 DataSentry 自动执行白名单 |
| `xsync` | 高 | 可向三台主机分发任意文件并创建目录，失败会产生配置不一致 | 永不进入 DataSentry 自动执行白名单 |

## 自动化准入结论

当前准入结论：

- 不开放生产写 Runbook。
- 不允许 DataSentry 调用 `/root/bin` 中任何脚本。
- 不允许把 `xcall`、`xsync` 或跨节点 root SSH 包装成白名单工具。
- 不允许把 `job.sh` 包装成“低风险重提作业” Runbook，除非先实现同名 Job 检测、审批、幂等键、回滚和操作后验证。
- 不允许继续用 root 运行 Spring API 或 AI Engine 作为长期生产形态。

最低准入条件：

1. 脚本迁出 root 私有目录，来源纳入 Git 或受控发布包。
2. 使用专用低权限服务用户运行应用。
3. 每个写动作都有审批、幂等、防重复、回滚和操作后验证。
4. 所有 secret 只来自受限文件或进程环境，输出必须脱敏。
5. 跨节点操作不得依赖 root 无密 SSH。
6. 通过 DataSentry 固定只读巡检和 M9 smoke 验证。

## 后续整改顺序

1. 保持 M9-R7 为未关闭状态，但把证据更新为“已完成源码初审，禁止自动执行”。
2. 下次 `data1` 打开后，只读复核 `/root/bin` 文件清单、权限、mtime 和哈希，确认是否与本报告一致。
3. 优先迁移 `spring.sh` 和 `ai.sh` 到 systemd + 专用服务用户 + loopback 监听。
4. 为 `job.sh` 设计只读检查优先的人工 Runbook：先列出当前 Flink Job，再决定是否人工提交。
5. 对 `doris.sh`、`flink.sh`、`xcall`、`xsync` 保持禁止自动执行；若确需保留，明确标注“人工维护窗口工具”。
6. 删除或迁出 `job.sh.bak-20260630-password-rotation` 这类旧备份脚本，避免误用。
