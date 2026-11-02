-- Apply after 001 and 003. Current signals are separate from immutable review evidence.
-- A listing can leave the publication without deleting its review/audit history.
ALTER TABLE api_review_queue ADD COLUMN IF NOT EXISTS listing_snapshot jsonb;
UPDATE api_review_queue q SET listing_snapshot = p.document
    FROM api_listing_projection p WHERE q.listing_id = p.id AND q.listing_snapshot IS NULL;
ALTER TABLE api_review_queue ALTER COLUMN listing_snapshot SET NOT NULL;
ALTER TABLE api_review_queue DROP CONSTRAINT IF EXISTS api_review_queue_listing_id_fkey;

CREATE TABLE IF NOT EXISTS api_listing_signals (
    id uuid PRIMARY KEY,
    listing_id uuid NOT NULL REFERENCES api_listing_projection(id) ON DELETE CASCADE,
    document jsonb NOT NULL CHECK (jsonb_typeof(document) = 'object'),
    active boolean NOT NULL DEFAULT true,
    last_evaluated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (document->>'id' = id::text),
    CHECK (document->>'listing_id' = listing_id::text)
);
CREATE INDEX IF NOT EXISTS api_listing_signals_current
    ON api_listing_signals(listing_id, id) WHERE active;
CREATE INDEX IF NOT EXISTS api_review_signal_membership
    ON api_review_queue USING gin(signal_ids);

-- Retire published signals immediately when their inputs change, before the next producer run.
CREATE OR REPLACE FUNCTION invalidate_listing_signals() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.document -> 'status' IS DISTINCT FROM OLD.document -> 'status'
       OR (SELECT jsonb_object_agg(k, NEW.document -> k) IS DISTINCT FROM
                  jsonb_object_agg(k, OLD.document -> k)
           FROM unnest(ARRAY['latitude', 'longitude', 'district_id', 'area_sqm', 'rooms',
                            'floor', 'total_floors', 'title', 'description',
                            'coordinate_confidence', 'price_monthly_normalized']) AS k)
    THEN
        UPDATE api_listing_signals SET active = false WHERE listing_id = NEW.id AND active;
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS api_invalidate_listing_signals ON api_listing_projection;
CREATE TRIGGER api_invalidate_listing_signals AFTER UPDATE ON api_listing_projection
    FOR EACH ROW EXECUTE FUNCTION invalidate_listing_signals();
