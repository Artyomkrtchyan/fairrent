-- C04 immutable valuation audit records. No stored result is served as a cache.
CREATE TABLE IF NOT EXISTS api_valuation_estimates (
    request_id uuid PRIMARY KEY,
    generated_at timestamptz NOT NULL,
    data_as_of timestamptz,
    dataset_version text NOT NULL,
    model_version text NOT NULL,
    policy_version text NOT NULL,
    coverage_version text NOT NULL,
    request_document jsonb NOT NULL,
    response_document jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS api_valuation_estimates_generated_idx
    ON api_valuation_estimates (generated_at DESC);

CREATE INDEX IF NOT EXISTS api_listing_valuation_location
    ON api_listing_projection USING gist
    ((ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography))
    WHERE status = 'active' AND latitude IS NOT NULL AND longitude IS NOT NULL;
