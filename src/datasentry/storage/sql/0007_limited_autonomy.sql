CREATE TABLE autonomy_policies (
    runbook_name TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
    shadow_mode INTEGER NOT NULL CHECK (shadow_mode IN (0, 1)),
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE autonomy_runs (
    id TEXT PRIMARY KEY,
    runbook_name TEXT NOT NULL CHECK (length(trim(runbook_name)) > 0),
    target TEXT NOT NULL CHECK (length(trim(target)) > 0),
    incident_id TEXT,
    operation_id TEXT,
    decision_status TEXT NOT NULL CHECK (
        decision_status IN ('allowed', 'shadowed', 'blocked', 'escalated')
    ),
    reason_code TEXT NOT NULL CHECK (length(trim(reason_code)) > 0),
    reason TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    created_at TEXT NOT NULL,
    finished_at TEXT,
    succeeded INTEGER CHECK (succeeded IN (0, 1)),
    payload_json TEXT NOT NULL
);

CREATE INDEX idx_autonomy_runs_created_at
    ON autonomy_runs(created_at DESC);

CREATE INDEX idx_autonomy_runs_runbook_created_at
    ON autonomy_runs(runbook_name, created_at DESC);

CREATE INDEX idx_autonomy_runs_allowed_scope
    ON autonomy_runs(runbook_name, target, incident_id, created_at DESC)
    WHERE decision_status = 'allowed';

CREATE TABLE autonomy_circuit_breakers (
    runbook_name TEXT PRIMARY KEY,
    state TEXT NOT NULL CHECK (state IN ('closed', 'open', 'half_open')),
    failure_count INTEGER NOT NULL CHECK (failure_count >= 0),
    opened_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE autonomy_rate_counters (
    scope TEXT NOT NULL CHECK (scope IN ('per_runbook', 'per_target', 'per_incident')),
    counter_key TEXT NOT NULL CHECK (length(trim(counter_key)) > 0),
    window_started_at TEXT NOT NULL,
    count INTEGER NOT NULL CHECK (count >= 0),
    PRIMARY KEY (scope, counter_key, window_started_at)
);
