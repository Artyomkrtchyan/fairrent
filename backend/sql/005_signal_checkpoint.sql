-- Applied by the schema owner. The worker needs SELECT, INSERT and UPDATE.
CREATE TABLE IF NOT EXISTS api_signal_checkpoints (
    context_key text PRIMARY KEY,
    inventory_key text NOT NULL,
    as_of timestamptz NOT NULL,
    last_listing_id uuid,
    counts jsonb NOT NULL DEFAULT '{}'::jsonb,
    completed boolean NOT NULL DEFAULT false,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
