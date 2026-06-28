CREATE TABLE runbooks (
    name TEXT PRIMARY KEY,
    version TEXT NOT NULL CHECK (length(trim(version)) > 0),
    title TEXT NOT NULL CHECK (length(trim(title)) > 0),
    description TEXT NOT NULL CHECK (length(trim(description)) > 0),
    risk TEXT NOT NULL CHECK (risk IN ('L0', 'L1', 'L2', 'L3', 'forbidden')),
    execution_mode TEXT NOT NULL CHECK (execution_mode IN ('mock', 'forbidden')),
    parameter_schema_json TEXT NOT NULL,
    precheck_json TEXT NOT NULL,
    postcheck_json TEXT NOT NULL,
    lock_key_template TEXT NOT NULL CHECK (length(trim(lock_key_template)) > 0),
    idempotency_key_template TEXT NOT NULL CHECK (length(trim(idempotency_key_template)) > 0),
    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
    audit_notes TEXT
);

CREATE TABLE operation_events (
    id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    summary TEXT NOT NULL CHECK (length(trim(summary)) > 0),
    actor TEXT NOT NULL CHECK (length(trim(actor)) > 0),
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (operation_id) REFERENCES operations(id) ON DELETE CASCADE
);

CREATE TABLE operation_locks (
    id TEXT PRIMARY KEY,
    lock_key TEXT NOT NULL CHECK (length(trim(lock_key)) > 0),
    operation_id TEXT NOT NULL,
    runbook_name TEXT NOT NULL CHECK (length(trim(runbook_name)) > 0),
    target TEXT NOT NULL CHECK (length(trim(target)) > 0),
    acquired_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    released_at TEXT,
    FOREIGN KEY (operation_id) REFERENCES operations(id) ON DELETE CASCADE
);

CREATE INDEX idx_operation_events_operation_id_created_at
    ON operation_events(operation_id, created_at);
CREATE UNIQUE INDEX idx_operation_locks_active_lock_key
    ON operation_locks(lock_key)
    WHERE released_at IS NULL;
