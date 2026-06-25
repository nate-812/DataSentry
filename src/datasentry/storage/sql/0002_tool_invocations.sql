CREATE TABLE tool_invocations (
    id TEXT PRIMARY KEY,
    inspection_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    target TEXT NOT NULL CHECK (length(trim(target)) > 0),
    parameters_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('succeeded', 'failed')),
    observation_count INTEGER NOT NULL CHECK (observation_count >= 0),
    error_code TEXT,
    error_message TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    duration_ms INTEGER NOT NULL CHECK (duration_ms >= 0),
    FOREIGN KEY (inspection_id) REFERENCES inspections(id) ON DELETE CASCADE,
    CHECK (
        (status = 'succeeded' AND error_code IS NULL AND error_message IS NULL)
        OR
        (status = 'failed' AND error_code IS NOT NULL AND error_message IS NOT NULL)
    )
);

CREATE INDEX idx_tool_invocations_inspection_started
    ON tool_invocations(inspection_id, started_at);
