ALTER TABLE operations ADD COLUMN idempotency_key TEXT;

CREATE UNIQUE INDEX idx_operations_idempotency_key_active
    ON operations(idempotency_key)
    WHERE idempotency_key IS NOT NULL
      AND status IN ('requested', 'awaiting_approval', 'approved', 'running', 'verifying');
