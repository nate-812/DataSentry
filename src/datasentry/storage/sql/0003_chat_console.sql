CREATE TABLE chat_sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL CHECK (length(trim(title)) > 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE chat_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL CHECK (length(trim(content)) > 0),
    inspection_id TEXT,
    llm_status TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (inspection_id) REFERENCES inspections(id) ON DELETE SET NULL
);

CREATE TABLE chat_runs (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_message_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    inspection_id TEXT,
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    finished_at TEXT,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (user_message_id) REFERENCES chat_messages(id) ON DELETE CASCADE,
    FOREIGN KEY (inspection_id) REFERENCES inspections(id) ON DELETE SET NULL,
    CHECK (
        (status != 'failed' AND error_code IS NULL AND error_message IS NULL)
        OR
        (
            status = 'failed'
            AND error_code IS NOT NULL
            AND length(trim(error_code)) > 0
            AND error_message IS NOT NULL
            AND length(trim(error_message)) > 0
        )
    )
);

CREATE TABLE chat_run_events (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (
        event_type IN (
            'accepted',
            'knowledge_loaded',
            'tools_planned',
            'tool_started',
            'tool_finished',
            'rules_completed',
            'llm_started',
            'llm_completed',
            'completed',
            'failed'
        )
    ),
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES chat_runs(id) ON DELETE CASCADE
);

CREATE INDEX idx_chat_sessions_updated_at
    ON chat_sessions(updated_at);
CREATE INDEX idx_chat_messages_session_created
    ON chat_messages(session_id, created_at);
CREATE INDEX idx_chat_runs_session_created
    ON chat_runs(session_id, created_at);
CREATE INDEX idx_chat_run_events_run_created
    ON chat_run_events(run_id, created_at);
