-- C05 foundation. Apply after 001; safe to rerun. No real users or queue seeds.
CREATE TABLE IF NOT EXISTS api_reviewer_sessions (
    id uuid PRIMARY KEY,
    token_hash text NOT NULL UNIQUE CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    actor_id uuid NOT NULL,
    role text NOT NULL CHECK (role IN ('reviewer', 'viewer')),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    CHECK (expires_at > created_at)
);
CREATE TABLE IF NOT EXISTS api_review_queue (
    id uuid PRIMARY KEY,
    listing_id uuid NOT NULL REFERENCES api_listing_projection(id),
    signal_ids uuid[] NOT NULL CHECK (cardinality(signal_ids) > 0),
    signals jsonb NOT NULL CHECK (jsonb_typeof(signals) = 'array' AND jsonb_array_length(signals) = cardinality(signal_ids)),
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'in_review', 'resolved')),
    decision text CHECK (decision IN ('dismissed', 'needs_follow_up', 'confirmed_issue')),
    reason text CHECK (length(reason) BETWEEN 1 AND 2000 AND reason ~ '\S'),
    reviewed_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version integer NOT NULL DEFAULT 1 CHECK (version >= 1),
    CHECK ((status = 'resolved') = (decision IS NOT NULL)),
    CHECK ((status = 'resolved') = (reviewed_at IS NOT NULL)),
    CHECK (status = 'pending' OR reason IS NOT NULL)
);
CREATE UNIQUE INDEX IF NOT EXISTS api_review_one_open_per_listing
    ON api_review_queue(listing_id) WHERE status <> 'resolved';
CREATE INDEX IF NOT EXISTS api_review_order ON api_review_queue(status, updated_at DESC, id);
CREATE TABLE IF NOT EXISTS api_review_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    review_id uuid NOT NULL REFERENCES api_review_queue(id),
    status text NOT NULL CHECK (status IN ('in_review', 'resolved')),
    decision text CHECK (decision IN ('dismissed', 'needs_follow_up', 'confirmed_issue')),
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 2000 AND reason ~ '\S'),
    actor_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((status = 'resolved') = (decision IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS api_review_event_order ON api_review_events(review_id, id);
