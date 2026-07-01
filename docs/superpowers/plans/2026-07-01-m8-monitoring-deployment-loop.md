# M8 Monitoring Deployment Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a repeatable M8 validation loop for real Prometheus/Grafana/Alertmanager deployment checks and DataSentry Alertmanager diagnosis smoke tests.

**Architecture:** Add a small `datasentry.monitoring` package with pure validation logic and injectable HTTP clients. Wire it into Typer as `datasentry monitoring deployment-check` and `datasentry monitoring alert-smoke`, keep all production-facing operations read-only except the intentional DataSentry API smoke that creates local Incident/RCA records.

**Tech Stack:** Python 3.12, Pydantic v2, httpx, Typer, pytest, PyYAML, existing `DataSentryError` and redaction helpers.

---

## File Structure

- Create `config/monitoring.example.toml`: no-secret endpoint template for Prometheus, Grafana, Alertmanager, and DataSentry API.
- Create `src/datasentry/monitoring/__init__.py`: public exports.
- Create `src/datasentry/monitoring/config.py`: TOML loader and safe URL validation.
- Create `src/datasentry/monitoring/deployment.py`: read-only deployment checks and report models.
- Create `src/datasentry/monitoring/smoke.py`: Alertmanager → DataSentry API smoke checks and report models.
- Modify `src/datasentry/cli/app.py`: register `monitoring` Typer group and two commands.
- Modify `monitoring/alertmanager/alertmanager.example.yml`: fix DataSentry receiver URL to `/api/alertmanager/webhook`.
- Create `docs/operations/monitoring-deployment.md`: M8 operations guide.
- Modify `docs/PROJECT_STATUS.md`: add M8 snapshot, progress, doc links, and risk boundary.
- Create `tests/unit/monitoring/test_monitoring_config.py`: config parsing and safe URL tests.
- Create `tests/unit/monitoring/test_deployment_check.py`: deployment check tests with fake HTTP client.
- Create `tests/unit/monitoring/test_alert_smoke.py`: alert smoke tests with fake HTTP client.
- Create `tests/scenarios/test_cli_monitoring.py`: CLI scenario tests.
- Modify `tests/unit/monitoring/test_monitoring_assets.py`: assert Alertmanager example points to the real DataSentry route.

## Task 1: M8 Docs And Monitoring Config

**Files:**
- Create: `docs/superpowers/specs/2026-07-01-m8-monitoring-deployment-loop-design.md`
- Create: `docs/superpowers/plans/2026-07-01-m8-monitoring-deployment-loop.md`
- Create: `config/monitoring.example.toml`
- Test: `tests/unit/monitoring/test_monitoring_config.py`

- [ ] **Step 1: Write failing config tests**

Create tests that load `config/monitoring.example.toml`, assert all four base URLs parse, assert `KlineFreshnessStale` is in `expected_alerts`, and assert URLs containing credentials are rejected with `configuration.monitoring_invalid`.

- [ ] **Step 2: Run test to verify RED**

Run: `.venv/bin/pytest tests/unit/monitoring/test_monitoring_config.py -q`

Expected: FAIL because `datasentry.monitoring` does not exist.

- [ ] **Step 3: Implement config module**

Create `MonitoringDeploymentConfig`, `MonitoringEndpoints`, and `load_monitoring_deployment_config`. URL validation rejects credentials, query, and fragment.

- [ ] **Step 4: Run test to verify GREEN**

Run: `.venv/bin/pytest tests/unit/monitoring/test_monitoring_config.py -q`

Expected: PASS.

## Task 2: Deployment Check Domain

**Files:**
- Create: `src/datasentry/monitoring/deployment.py`
- Modify: `src/datasentry/monitoring/__init__.py`
- Test: `tests/unit/monitoring/test_deployment_check.py`

- [ ] **Step 1: Write failing deployment tests**

Use a fake HTTP client returning safe response objects. Cover:

- all checks pass when Prometheus readiness, rules, Alertmanager readiness/status, and Grafana health are healthy;
- report fails when Prometheus rules omit `KlineFreshnessStale`;
- report fails when Alertmanager config omits `/api/alertmanager/webhook`.

- [ ] **Step 2: Run test to verify RED**

Run: `.venv/bin/pytest tests/unit/monitoring/test_deployment_check.py -q`

Expected: FAIL because deployment check functions are missing.

- [ ] **Step 3: Implement deployment checks**

Add `MonitoringCheckStatus`, `MonitoringCheckResult`, `MonitoringDeploymentReport`, `HttpProbeClient`, `HttpProbeResponse`, `HttpxProbeClient`, and `run_monitoring_deployment_check`.

- [ ] **Step 4: Run test to verify GREEN**

Run: `.venv/bin/pytest tests/unit/monitoring/test_deployment_check.py -q`

Expected: PASS.

## Task 3: Alertmanager Smoke Domain

**Files:**
- Create: `src/datasentry/monitoring/smoke.py`
- Modify: `src/datasentry/monitoring/__init__.py`
- Test: `tests/unit/monitoring/test_alert_smoke.py`

- [ ] **Step 1: Write failing smoke tests**

Use a fake HTTP client. Cover complete flow:

- POST webhook returns accepted and incident id;
- detail route returns incident id;
- timeline contains an alert event;
- RCA route returns markdown;
- export route returns Markdown text.

Also cover webhook rejection producing a failed report without leaking payload contents.

- [ ] **Step 2: Run test to verify RED**

Run: `.venv/bin/pytest tests/unit/monitoring/test_alert_smoke.py -q`

Expected: FAIL because smoke functions are missing.

- [ ] **Step 3: Implement smoke checks**

Add `AlertSmokeStep`, `AlertSmokeReport`, `HttpSmokeClient`, `HttpxSmokeClient`, and `run_alertmanager_smoke`.

- [ ] **Step 4: Run test to verify GREEN**

Run: `.venv/bin/pytest tests/unit/monitoring/test_alert_smoke.py -q`

Expected: PASS.

## Task 4: CLI And Monitoring Assets

**Files:**
- Modify: `src/datasentry/cli/app.py`
- Modify: `monitoring/alertmanager/alertmanager.example.yml`
- Test: `tests/scenarios/test_cli_monitoring.py`
- Test: `tests/unit/monitoring/test_monitoring_assets.py`

- [ ] **Step 1: Write failing CLI tests**

Use monkeypatched fake runner functions in `datasentry.cli.app` and assert:

- `datasentry monitoring deployment-check --config-file config/monitoring.example.toml` prints report JSON;
- `datasentry monitoring alert-smoke --config-file config/monitoring.example.toml --payload-file tests/fixtures/alertmanager/kline_freshness_firing.json` prints report JSON;
- failed reports exit with code 2.

- [ ] **Step 2: Add asset regression**

Update monitoring asset tests so `alertmanager.example.yml` must contain `/api/alertmanager/webhook`.

- [ ] **Step 3: Run tests to verify RED**

Run: `.venv/bin/pytest tests/scenarios/test_cli_monitoring.py tests/unit/monitoring/test_monitoring_assets.py -q`

Expected: FAIL because CLI commands and route fix are missing.

- [ ] **Step 4: Wire CLI and fix Alertmanager route**

Register `monitoring_app`, add `MonitoringConfigFileOption`, implement `deployment-check` and `alert-smoke`, and update the example receiver URL.

- [ ] **Step 5: Run tests to verify GREEN**

Run: `.venv/bin/pytest tests/scenarios/test_cli_monitoring.py tests/unit/monitoring/test_monitoring_assets.py -q`

Expected: PASS.

## Task 5: Operations Guide And Project Status

**Files:**
- Create: `docs/operations/monitoring-deployment.md`
- Modify: `README.md`
- Modify: `docs/PROJECT_STATUS.md`

- [ ] **Step 1: Write operations guide**

Document safe deployment validation commands, evidence capture, expected outputs, and the boundary that deployment and secret injection remain outside DataSentry.

- [ ] **Step 2: Link docs**

Link the guide from README and add M8 spec/plan to project status key docs.

- [ ] **Step 3: Update status snapshot**

Mark M8 as implemented in code but not yet live-validated against the real deployed monitoring stack unless a live smoke is run during this milestone.

## Task 6: Final Verification

**Files:**
- All changed files.

- [ ] **Step 1: Run focused checks**

Run:

```bash
.venv/bin/pytest tests/unit/monitoring tests/scenarios/test_cli_monitoring.py tests/integration/api/test_alertmanager_api.py -q
```

Expected: PASS.

- [ ] **Step 2: Run static checks**

Run:

```bash
.venv/bin/ruff format --check .
.venv/bin/ruff check .
.venv/bin/mypy src
```

Expected: PASS.

- [ ] **Step 3: Run full pytest**

Run:

```bash
.venv/bin/pytest tests -q -W error::ResourceWarning --cov=datasentry --cov-report=term-missing --cov-fail-under=90
```

Expected: PASS with coverage at or above 90%.

- [ ] **Step 4: Inspect diff and commit**

Run:

```bash
git diff --check
git status --short
```

Commit:

```bash
git add config docs monitoring src tests README.md
git commit -m "feat: 增加M8监控部署闭环验收"
```
