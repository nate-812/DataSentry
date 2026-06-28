CREATE TABLE incident_links (
    id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (
        kind IN ('inspection', 'finding', 'operation', 'alert', 'chat_run', 'rca_report')
    ),
    target_id TEXT NOT NULL CHECK (length(trim(target_id)) > 0),
    summary TEXT NOT NULL CHECK (length(trim(summary)) > 0),
    created_at TEXT NOT NULL,
    FOREIGN KEY (incident_id) REFERENCES incidents(id) ON DELETE CASCADE,
    UNIQUE (incident_id, kind, target_id)
);

CREATE TABLE incident_timeline_events (
    id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (
        event_type IN (
            'alert_fired',
            'alert_resolved',
            'diagnosis_started',
            'diagnosis_completed',
            'diagnosis_failed',
            'finding_added',
            'operation_linked',
            'status_changed',
            'verification_completed',
            'rca_generated',
            'manual_note_added'
        )
    ),
    summary TEXT NOT NULL CHECK (length(trim(summary)) > 0),
    source TEXT NOT NULL CHECK (length(trim(source)) > 0),
    payload_json TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    FOREIGN KEY (incident_id) REFERENCES incidents(id) ON DELETE CASCADE
);

CREATE TABLE incident_fingerprints (
    id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    component TEXT NOT NULL CHECK (length(trim(component)) > 0),
    failure_type TEXT NOT NULL CHECK (length(trim(failure_type)) > 0),
    stable_labels_hash TEXT NOT NULL CHECK (length(trim(stable_labels_hash)) > 0),
    severity TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    FOREIGN KEY (incident_id) REFERENCES incidents(id) ON DELETE CASCADE,
    UNIQUE (incident_id, component, failure_type, stable_labels_hash)
);

CREATE TABLE incident_rca_reports (
    id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    markdown TEXT NOT NULL CHECK (length(trim(markdown)) > 0),
    structured_json TEXT NOT NULL,
    generated_by TEXT NOT NULL CHECK (length(trim(generated_by)) > 0),
    created_at TEXT NOT NULL,
    FOREIGN KEY (incident_id) REFERENCES incidents(id) ON DELETE CASCADE,
    UNIQUE (incident_id, version)
);

CREATE INDEX idx_incident_links_incident_kind
    ON incident_links(incident_id, kind);
CREATE INDEX idx_incident_timeline_incident_time
    ON incident_timeline_events(incident_id, occurred_at);
CREATE INDEX idx_incident_fingerprints_lookup
    ON incident_fingerprints(component, failure_type, stable_labels_hash, last_seen_at);
CREATE INDEX idx_incident_rca_incident_version
    ON incident_rca_reports(incident_id, version);
