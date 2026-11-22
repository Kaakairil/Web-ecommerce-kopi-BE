-- 0007: event outbox (webhook delivery with retries / dead-letter)
CREATE TABLE IF NOT EXISTS events (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_type     TEXT NOT NULL,
    payload        JSONB NOT NULL,
    status         TEXT NOT NULL DEFAULT 'pending',  -- pending | delivered | dead
    attempts       INT NOT NULL DEFAULT 0,
    last_error     TEXT,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    delivered_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_events_status ON events (status, next_attempt_at);
