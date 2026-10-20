-- Backend-owned read projection, independent of A02 tables.
-- Apply explicitly before serving C03. Does not seed or alter source inventory.
CREATE TABLE IF NOT EXISTS api_listing_projection (
    id uuid PRIMARY KEY,
    source text NOT NULL CHECK (source = 'list.am'),
    external_id text NOT NULL,
    status text NOT NULL CHECK (status IN ('active', 'inactive')),
    district_id text,
    price numeric CHECK (price > 0),
    area numeric CHECK (area > 0),
    rooms integer CHECK (rooms >= 1),
    latitude double precision CHECK (latitude BETWEEN -90 AND 90),
    longitude double precision CHECK (longitude BETWEEN -180 AND 180),
    newest_at timestamptz NOT NULL,
    document jsonb NOT NULL,
    UNIQUE (source, external_id),
    CHECK ((latitude IS NULL) = (longitude IS NULL)),
    CHECK (document->>'id' = id::text),
    CHECK (document->>'source' = source),
    CHECK (document->>'external_id' = external_id)
);
CREATE INDEX IF NOT EXISTS api_listing_newest ON api_listing_projection (status, newest_at DESC, id);
CREATE INDEX IF NOT EXISTS api_listing_price ON api_listing_projection (status, price, id);
CREATE INDEX IF NOT EXISTS api_listing_area ON api_listing_projection (status, area, id);
CREATE INDEX IF NOT EXISTS api_listing_district ON api_listing_projection (status, district_id);
CREATE INDEX IF NOT EXISTS api_listing_coordinates ON api_listing_projection (longitude, latitude)
    WHERE longitude IS NOT NULL AND latitude IS NOT NULL;
