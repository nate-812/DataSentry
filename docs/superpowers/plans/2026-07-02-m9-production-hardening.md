# M9 Production Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the repository artifacts and validation path needed to run DataSentry API on `data1` as a loopback-only systemd service and wire Alertmanager to call it locally.

**Architecture:** M9 stays documentation-and-deployment-asset first: add no-secret systemd and environment examples, tests that protect loopback binding and secret hygiene, and operations guides for deploy, rollback, exposure review, and smoke validation. Cloud execution remains a separate user-approved phase after repository artifacts pass local checks.

**Tech Stack:** Python 3.12, pytest, existing CLI commands (`datasentry ops preflight`, `datasentry monitoring deployment-check`, `datasentry monitoring alert-smoke`, `datasentry inspection run`), systemd unit examples, Markdown operations docs.

---

## File Structure

- Create `deploy/systemd/datasentry-api.service.example`: no-secret systemd service example for `data1`, bound to `127.0.0.1:18000`.
- Create `config/datasentry.env.example`: no-secret production environment template for DataSentry API.
- Create `docs/operations/m9-production-deployment.md`: deploy, smoke, rollback, and evidence guide.
- Create `docs/operations/production-exposure-checklist.md`: manual checklist for public exposure, account, secret, and monitoring regression review.
- Create `tests/unit/test_deployment_assets.py`: regression tests for service/env examples and documentation links.
- Modify `README.md`: add M9 usage section and link operations docs.
- Modify `docs/PROJECT_STATUS.md`: mark M9 implementation artifacts in progress and add plan/doc links.

## Task 1: Deployment Asset Regression Tests

**Files:**
- Create: `tests/unit/test_deployment_assets.py`

- [ ] **Step 1: Write failing tests for M9 assets**

Create `tests/unit/test_deployment_assets.py` with:

```python
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_datasentry_systemd_example_is_loopback_only_and_uses_env_file() -> None:
    service = read_text("deploy/systemd/datasentry-api.service.example")

    assert "User=datasentry" in service
    assert "Group=datasentry" in service
    assert "EnvironmentFile=/etc/datasentry/datasentry.env" in service
    assert "--host 127.0.0.1" in service
    assert "--port 18000" in service
    assert "0.0.0.0" not in service
    assert "DATASENTRY_DORIS_PASSWORD" not in service
    assert "DATASENTRY_MYSQL_PASSWORD" not in service
    assert "DATASENTRY_REDIS_PASSWORD" not in service


def test_datasentry_env_example_contains_only_safe_placeholders() -> None:
    env = read_text("config/datasentry.env.example")

    assert "DATASENTRY_ENVIRONMENT=production" in env
    assert "DATASENTRY_API_HOST=127.0.0.1" in env
    assert "DATASENTRY_API_PORT=18000" in env
    assert "DATASENTRY_DATABASE_PATH=/var/lib/datasentry/datasentry.db" in env
    assert "DATASENTRY_TARGETS_FILE=/etc/datasentry/targets.toml" in env
    assert "DATASENTRY_LLM_PROVIDER=mock" in env
    forbidden_fragments = [
        "password=",
        "token=",
        "secret=",
        "DATASENTRY_DORIS_PASSWORD=",
        "DATASENTRY_MYSQL_PASSWORD=",
        "DATASENTRY_REDIS_PASSWORD=",
        "DATASENTRY_LLM_API_KEY=",
    ]
    lower_env = env.lower()
    for fragment in forbidden_fragments:
        assert fragment.lower() not in lower_env


def test_m9_operations_docs_link_required_smoke_commands() -> None:
    guide = read_text("docs/operations/m9-production-deployment.md")
    checklist = read_text("docs/operations/production-exposure-checklist.md")

    assert "systemctl status datasentry-api" in guide
    assert "curl -fsS http://127.0.0.1:18000/api/health" in guide
    assert "datasentry monitoring deployment-check" in guide
    assert "datasentry monitoring alert-smoke" in guide
    assert "datasentry inspection run" in guide
    assert "127.0.0.1:18000" in guide
    assert "Flink Web" in checklist
    assert "Doris FE" in checklist
    assert "MySQL" in checklist
    assert "Redis" in checklist
    assert "Spring API" in checklist
    assert "AI Engine" in checklist
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
.venv/bin/pytest tests/unit/test_deployment_assets.py -q
```

Expected: FAIL because the M9 deployment assets do not exist yet.

- [ ] **Step 3: Commit test-only checkpoint**

Run:

```bash
git add tests/unit/test_deployment_assets.py
git commit -m "test: 增加M9部署资产回归测试"
```

Expected: commit succeeds with only the new failing tests. If the team prefers not to commit red tests, keep this step unstaged and commit Task 1 together with Task 2 after the tests pass.

## Task 2: Systemd And Environment Examples

**Files:**
- Create: `deploy/systemd/datasentry-api.service.example`
- Create: `config/datasentry.env.example`
- Test: `tests/unit/test_deployment_assets.py`

- [ ] **Step 1: Create systemd service example**

Create `deploy/systemd/datasentry-api.service.example`:

```ini
[Unit]
Description=DataSentry API
Documentation=https://github.com/nate-812/DataSentry
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=datasentry
Group=datasentry
WorkingDirectory=/opt/datasentry-agent
EnvironmentFile=/etc/datasentry/datasentry.env
ExecStart=/opt/datasentry-agent/.venv/bin/uvicorn datasentry.api:create_app --factory --host 127.0.0.1 --port 18000
Restart=on-failure
RestartSec=5
TimeoutStopSec=20
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/datasentry /var/log/datasentry
MemoryMax=768M
CPUQuota=80%

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Create no-secret env example**

Create `config/datasentry.env.example`:

```bash
# DataSentry API production environment example.
# Copy to /etc/datasentry/datasentry.env on data1 and restrict permissions.
# Do not commit the real production file.

DATASENTRY_ENVIRONMENT=production
DATASENTRY_API_HOST=127.0.0.1
DATASENTRY_API_PORT=18000
DATASENTRY_DATABASE_PATH=/var/lib/datasentry/datasentry.db
DATASENTRY_TARGETS_FILE=/etc/datasentry/targets.toml
DATASENTRY_LOG_LEVEL=INFO
DATASENTRY_LOG_FORMAT=json
DATASENTRY_LLM_PROVIDER=mock
DATASENTRY_GRAFANA_URL=http://127.0.0.1:3000
```

Do not add `DATASENTRY_DORIS_PASSWORD`, `DATASENTRY_MYSQL_PASSWORD`, `DATASENTRY_REDIS_PASSWORD`, or `DATASENTRY_LLM_API_KEY` to this example. The operations guide explains that real values belong only in the restricted cloud file.

- [ ] **Step 3: Run asset tests to verify GREEN for service/env**

Run:

```bash
.venv/bin/pytest tests/unit/test_deployment_assets.py -q
```

Expected: still FAIL only on missing operations docs; systemd and env assertions pass.

- [ ] **Step 4: Commit service/env checkpoint**

Run:

```bash
git add deploy/systemd/datasentry-api.service.example config/datasentry.env.example tests/unit/test_deployment_assets.py
git commit -m "chore: 增加M9云端API部署示例"
```

Expected: commit succeeds. If Task 1 was not committed separately, include `tests/unit/test_deployment_assets.py` here.

## Task 3: Operations Guide And Exposure Checklist

**Files:**
- Create: `docs/operations/m9-production-deployment.md`
- Create: `docs/operations/production-exposure-checklist.md`
- Test: `tests/unit/test_deployment_assets.py`

- [ ] **Step 1: Write M9 deployment guide**

Create `docs/operations/m9-production-deployment.md` with:

```markdown
# M9 生产化部署运维手册

本文档说明如何把 DataSentry API 作为 `data1` 本机 loopback 服务运行，并让 Alertmanager 通过本机地址回调。开发、提交和版本管理仍以本地仓库和 GitHub 为准；云端只运行明确 Git 版本。

## 安全边界

允许：

- 以独立系统用户运行 DataSentry API。
- 让 API 只监听 `127.0.0.1:18000`。
- 让 Alertmanager 调用 `http://127.0.0.1:18000/api/alertmanager/webhook`。
- 使用固定只读工具执行巡检。
- 在 DataSentry SQLite 中保存 Incident、timeline、RCA 和 evidence。

不允许：

- 直接暴露 DataSentry API、Grafana、Prometheus、Alertmanager、Flink Web、Doris FE、MySQL、Redis、Spring API 或 AI Engine 到公网。
- 写入生产数据库、执行任意 Shell、自动重启、自动补数、自动改配置或自动 Savepoint 恢复。
- 把真实 secret 写入 Git、README、Issue、PR、SQLite、RCA、日志或命令输出。

## 云端目录

建议在 `data1` 使用：

```text
/opt/datasentry-agent/
/var/lib/datasentry/
/var/log/datasentry/
/etc/datasentry/datasentry.env
/etc/datasentry/targets.toml
```

`/etc/datasentry/datasentry.env` 和 `/etc/datasentry/targets.toml` 是云端真实配置，不提交到 Git。

## 仓库产物

```bash
deploy/systemd/datasentry-api.service.example
config/datasentry.env.example
docs/operations/production-exposure-checklist.md
```

## 部署前确认

```bash
git status --short --branch
git rev-parse --short HEAD
git diff --check
```

记录将部署的 Git commit。不要部署未提交或来源不明的工作区。

## systemd 安装

以下命令展示步骤，不包含真实 secret。执行云端写操作前必须由用户再次确认。

```bash
sudo install -o root -g root -m 0644 \
  deploy/systemd/datasentry-api.service.example \
  /etc/systemd/system/datasentry-api.service

sudo install -o root -g datasentry -m 0640 \
  config/datasentry.env.example \
  /etc/datasentry/datasentry.env
```

编辑 `/etc/datasentry/datasentry.env` 时只在云端受限文件中加入真实 secret。不要把真实值复制回仓库。

## 启动和健康检查

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now datasentry-api
systemctl status datasentry-api
curl -fsS http://127.0.0.1:18000/api/health
```

`systemctl status` 和 `curl` 输出只能记录服务状态、HTTP 状态和脱敏摘要。

## Alertmanager 回调

将 DataSentry receiver 指向：

```yaml
webhook_configs:
  - url: http://127.0.0.1:18000/api/alertmanager/webhook
```

变更前备份 Alertmanager 配置。变更后先检查 readiness，再做 smoke。

## M9 回归

```bash
datasentry ops preflight \
  --targets-file /etc/datasentry/targets.toml

datasentry monitoring deployment-check \
  --config-file /etc/datasentry/monitoring.toml

datasentry monitoring alert-smoke \
  --config-file /etc/datasentry/monitoring.toml \
  --payload-file tests/fixtures/alertmanager/kline_freshness_firing.json

datasentry inspection run \
  --question "为什么K线不更新" \
  --targets-file /etc/datasentry/targets.toml \
  --knowledge-root knowledge \
  --database-path /var/lib/datasentry/datasentry.db
```

记录 Incident id、Inspection id、整体状态和失败项，不记录真实 secret。

## 本地访问

本地查看 API 或控制台时继续使用 SSH tunnel：

```bash
ssh -L 18000:127.0.0.1:18000 data1
```

Grafana、Prometheus 和 Alertmanager 继续通过各自 tunnel 访问，不开放公网。

## 回滚

```bash
sudo systemctl stop datasentry-api
sudo systemctl disable datasentry-api
```

然后将 Alertmanager receiver 恢复到变更前备份，reload 或重启 Alertmanager，并复查 readiness。保留 `/var/lib/datasentry/datasentry.db` 作为证据，除非用户明确要求清理。
```

- [ ] **Step 2: Write exposure checklist**

Create `docs/operations/production-exposure-checklist.md` with:

```markdown
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
```

- [ ] **Step 3: Run asset tests to verify GREEN**

Run:

```bash
.venv/bin/pytest tests/unit/test_deployment_assets.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit operations docs checkpoint**

Run:

```bash
git add docs/operations/m9-production-deployment.md docs/operations/production-exposure-checklist.md tests/unit/test_deployment_assets.py
git commit -m "docs: 增加M9生产部署手册"
```

Expected: commit succeeds.

## Task 4: README And Project Status

**Files:**
- Modify: `README.md`
- Modify: `docs/PROJECT_STATUS.md`

- [ ] **Step 1: Add README M9 section**

Add a new section after the M8 section in `README.md`:

```markdown
## M9 生产化与安全收口

M9 将 DataSentry API 作为 `data1` 本机 loopback 服务运行，让 Alertmanager 通过
`http://127.0.0.1:18000/api/alertmanager/webhook` 自动回调。开发和版本管理仍以
本地仓库与 GitHub 为准；云端只运行明确 Git 版本。

仓库提供无 secret 示例：

- `deploy/systemd/datasentry-api.service.example`
- `config/datasentry.env.example`
- `docs/operations/m9-production-deployment.md`
- `docs/operations/production-exposure-checklist.md`

M9 不开放任意 Shell、任意 SQL、生产写操作、自动重启、自动补数、自动改配置或
自动 Savepoint 恢复。DataSentry API、Prometheus、Grafana、Alertmanager、Flink Web、
Doris FE、MySQL、Redis、Spring API 和 AI Engine 不应直接暴露公网。
```

- [ ] **Step 2: Update project status snapshot**

In `docs/PROJECT_STATUS.md`:

- Update `当前工作` to mention M9 repository deployment artifacts are being implemented.
- Add the M9 implementation plan to `关键文档`.
- Add `docs/operations/m9-production-deployment.md` and `docs/operations/production-exposure-checklist.md` to `关键文档`.
- Keep the current risk that cloud deployment has not yet been executed.

- [ ] **Step 3: Run doc and asset checks**

Run:

```bash
.venv/bin/pytest tests/unit/test_deployment_assets.py -q
git diff --check
```

Expected: pytest PASS and `git diff --check` has no output.

- [ ] **Step 4: Commit docs/status checkpoint**

Run:

```bash
git add README.md docs/PROJECT_STATUS.md
git commit -m "docs: 补充M9生产化部署入口"
```

Expected: commit succeeds.

## Task 5: Final Verification And Handoff

**Files:**
- All changed files.

- [ ] **Step 1: Run focused verification**

Run:

```bash
.venv/bin/pytest tests/unit/test_deployment_assets.py tests/unit/monitoring tests/scenarios/test_cli_monitoring.py -q
```

Expected: PASS.

- [ ] **Step 2: Run formatting and static checks**

Run:

```bash
.venv/bin/ruff format --check .
.venv/bin/ruff check .
.venv/bin/mypy src
```

Expected: PASS.

- [ ] **Step 3: Run full test suite when time allows**

Run:

```bash
.venv/bin/pytest tests -q -W error::ResourceWarning --cov=datasentry --cov-report=term-missing --cov-fail-under=90
```

Expected: PASS with coverage at or above 90%.

- [ ] **Step 4: Secret and whitespace scan**

Run:

```bash
git diff --check
rg -n "DATASENTRY_DORIS_PASSWORD=|DATASENTRY_MYSQL_PASSWORD=|DATASENTRY_REDIS_PASSWORD=|DATASENTRY_LLM_API_KEY=|password=|token=|secret=|BEGIN .*PRIVATE" config deploy docs README.md tests
```

Expected: `git diff --check` has no output. `rg` may find explanatory text such as "do not commit secret" or test forbidden fragments, but no real secret values.

- [ ] **Step 5: Update project status before final commit if verification results changed**

If focused or full verification results differ from the current status snapshot, update `docs/PROJECT_STATUS.md` with:

- commands run;
- pass/fail result;
- whether cloud deployment has not yet been performed;
- current branch and latest local commit.

- [ ] **Step 6: Commit final verification status if needed**

Run only if Step 5 changed files:

```bash
git add docs/PROJECT_STATUS.md
git commit -m "docs: 记录M9部署资产验证结果"
```

Expected: commit succeeds.

- [ ] **Step 7: Handoff before cloud deployment**

Report:

- changed files;
- verification commands and results;
- current branch;
- latest commit hash;
- GitHub sync state;
- explicit statement that cloud deployment has not been executed yet.

Then ask the user whether to proceed to the `data1` cloud deployment validation phase.

## Self-Review

- Spec coverage: Tasks cover systemd service example, no-secret env example, deployment guide, rollback, exposure checklist, M9 regression commands, status updates, and local verification. Cloud deployment is deliberately excluded until user confirms after repository artifacts are complete.
- Placeholder scan: The plan contains no TBD/TODO markers. Ellipses are not used for command bodies. Secret-related strings appear only as forbidden test fragments or explanatory variable names without values.
- Type and path consistency: Paths match the design document: `127.0.0.1:18000`, `/etc/datasentry/datasentry.env`, `/etc/datasentry/targets.toml`, `/var/lib/datasentry/datasentry.db`, and `docs/operations/production-exposure-checklist.md`.
