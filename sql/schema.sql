-- Divergence Alert Microservice - PostgreSQL Schema
-- Run this to initialize the database.

BEGIN;

-- Users (Telegram users who receive alerts)
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL UNIQUE,
    username VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Per-user alert thresholds (admin defaults can be overridden)
CREATE TABLE IF NOT EXISTS user_thresholds (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    open_threshold NUMERIC NOT NULL,   -- divergence score above this => OPEN alert
    close_threshold NUMERIC NOT NULL, -- divergence score below this => CLOSED
    cooldown_minutes INTEGER NOT NULL DEFAULT 60,
    UNIQUE(user_id)
);

-- Time series snapshots (raw + normalized values for rolling z-score)
CREATE TABLE IF NOT EXISTS snapshots (
    id SERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    series_type VARCHAR(32) NOT NULL,  -- 'belief' | 'price'
    value_raw NUMERIC NOT NULL,
    value_change NUMERIC,              -- change from previous
    z_score NUMERIC,                   -- rolling z-score of change
    window_size INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_snapshots_ts ON snapshots(ts DESC);
CREATE INDEX IF NOT EXISTS idx_snapshots_series ON snapshots(series_type, ts DESC);

-- Divergence scores (computed each poll)
CREATE TABLE IF NOT EXISTS divergence_scores (
    id SERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    score NUMERIC NOT NULL,            -- z(belief change) - z(price change)
    belief_change NUMERIC,
    price_change NUMERIC,
    belief_z NUMERIC,
    price_z NUMERIC
);

CREATE INDEX IF NOT EXISTS idx_divergence_ts ON divergence_scores(ts DESC);

-- Alert lifecycle: OPEN -> UPDATE(s) -> CLOSED
CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status VARCHAR(16) NOT NULL DEFAULT 'OPEN',  -- OPEN | UPDATE | CLOSED
    divergence_score_id INTEGER REFERENCES divergence_scores(id),
    score_at_open NUMERIC,
    score_current NUMERIC,
    opened_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at TIMESTAMPTZ,
    cooldown_until TIMESTAMPTZ         -- no new OPEN until after this
);

CREATE INDEX IF NOT EXISTS idx_alerts_user_status ON alerts(user_id, status);
CREATE INDEX IF NOT EXISTS idx_alerts_cooldown ON alerts(user_id, cooldown_until);

-- Optional: audit log for alert state transitions
CREATE TABLE IF NOT EXISTS alert_events (
    id SERIAL PRIMARY KEY,
    alert_id INTEGER NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
    from_status VARCHAR(16),
    to_status VARCHAR(16) NOT NULL,
    score NUMERIC,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMIT;
