CREATE TABLE inspections (
    id TEXT PRIMARY KEY,
    question TEXT NOT NULL CHECK (length(trim(question)) > 0),
    scope_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    summary TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE TABLE observations (
    id TEXT PRIMARY KEY,
    inspection_id TEXT NOT NULL,
    component TEXT NOT NULL CHECK (length(trim(component)) > 0),
    metric_or_fact TEXT NOT NULL CHECK (length(trim(metric_or_fact)) > 0),
    value_json TEXT NOT NULL,
    source TEXT NOT NULL CHECK (length(trim(source)) > 0),
    target TEXT,
    observed_at TEXT NOT NULL,
    FOREIGN KEY (inspection_id) REFERENCES inspections(id) ON DELETE CASCADE
);

CREATE TABLE findings (
    id TEXT PRIMARY KEY,
    inspection_id TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
    status TEXT NOT NULL CHECK (
        status IN ('confirmed', 'inferred', 'unknown', 'historical')
    ),
    claim TEXT NOT NULL CHECK (length(trim(claim)) > 0),
    evidence_json TEXT NOT NULL,
    impact TEXT NOT NULL CHECK (length(trim(impact)) > 0),
    recommendation TEXT NOT NULL CHECK (length(trim(recommendation)) > 0),
    unknowns_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (inspection_id) REFERENCES inspections(id) ON DELETE CASCADE
);

CREATE TABLE incidents (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL CHECK (length(trim(title)) > 0),
    symptom TEXT NOT NULL CHECK (length(trim(symptom)) > 0),
    status TEXT NOT NULL CHECK (
        status IN (
            'open',
            'investigating',
            'awaiting_approval',
            'mitigating',
            'verifying',
            'resolved',
            'blocked',
            'escalated'
        )
    ),
    severity TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
    root_cause TEXT,
    opened_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE operations (
    id TEXT PRIMARY KEY,
    incident_id TEXT,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    version TEXT NOT NULL CHECK (length(trim(version)) > 0),
    parameters_json TEXT NOT NULL,
    risk TEXT NOT NULL CHECK (risk IN ('L0', 'L1', 'L2', 'L3', 'forbidden')),
    status TEXT NOT NULL CHECK (
        status IN (
            'requested',
            'awaiting_approval',
            'approved',
            'running',
            'verifying',
            'succeeded',
            'failed',
            'rejected',
            'cancelled'
        )
    ),
    requester TEXT NOT NULL CHECK (length(trim(requester)) > 0),
    approver TEXT,
    result_json TEXT,
    requested_at TEXT NOT NULL,
    approved_at TEXT,
    executed_at TEXT,
    verified_at TEXT,
    FOREIGN KEY (incident_id) REFERENCES incidents(id) ON DELETE SET NULL
);

CREATE INDEX idx_inspections_started_at
    ON inspections(started_at);
CREATE INDEX idx_observations_inspection_id
    ON observations(inspection_id);
CREATE INDEX idx_findings_inspection_id
    ON findings(inspection_id);
CREATE INDEX idx_incidents_status_updated_at
    ON incidents(status, updated_at);
CREATE INDEX idx_operations_status_requested_at
    ON operations(status, requested_at);
