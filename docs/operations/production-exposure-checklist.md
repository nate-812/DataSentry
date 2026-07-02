# 生产暴露面收口 Checklist

本文档用于 M9 和后续维护窗口的人工作业记录。它只描述检查项，不自动修改云安全组、主机防火墙或业务配置。

## 监听地址

- [ ] DataSentry API 只监听 `127.0.0.1:18000`。
- [ ] Prometheus 只监听 `127.0.0.1` 或内网地址。
- [ ] Grafana 只监听 `127.0.0.1` 或内网地址。
- [ ] Alertmanager 只监听 `127.0.0.1` 或内网地址。
- [ ] Flink Web 不直接暴露公网。
- [ ] Doris FE 不直接暴露公网。
- [ ] MySQL 不直接暴露公网。
- [ ] Redis 不直接暴露公网。
- [ ] Spring API 不直接暴露公网。
- [ ] AI Engine 不直接暴露公网。

## 账号权限

- [ ] SSH 日常巡检使用无 sudo、无写权限的只读账号。
- [ ] Doris/MySQL 诊断账号仅允许 `SELECT`、`SHOW` 和 `DESCRIBE`。
- [ ] Redis ACL 仅允许计划内只读命令，禁止 `KEYS`。
- [ ] root 只用于维护窗口、部署和受限 secret 初始化。

## secret 管理

- [ ] 真实 secret 只存在于云端受限文件或进程环境。
- [ ] 仓库中没有真实 `.env`、密码、token、Cookie、私钥或连接串。
- [ ] `datasentry ops preflight` 只展示变量名和 configured/missing 状态。
- [ ] 日志、RCA、通知和状态文档不记录 secret 值。

## 回归证据

- [ ] `systemctl status datasentry-api` 已检查。
- [ ] `curl -fsS http://127.0.0.1:18000/api/health` 已通过。
- [ ] `datasentry monitoring deployment-check` 已通过或失败项已记录。
- [ ] `datasentry monitoring alert-smoke` 已通过或失败项已记录。
- [ ] 真实 K 线只读巡检已通过或失败项已记录。
- [ ] AI Engine、MySQL 和 Redis 固定只读确认已执行或记录暂缓原因。

## 明确不在本轮处理

- [ ] Doris root 改密已单独排期，不混入 M9 API 部署。
- [ ] 云安全组变更已单独审批，不由 DataSentry 自动执行。
- [ ] 生产写 Runbook 仍未开放。
