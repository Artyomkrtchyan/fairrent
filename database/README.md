# Database

Schema, migrations, observation history, and geographic data. Model listings and physical properties separately.

Stack: PostgreSQL, PostGIS, SQLAlchemy, and Alembic; hosted on AWS RDS. See the [technology stack](../docs/technology-stack.md).

A07 publishes weekly asking-price aggregates in `weekly_neighborhood_price_indexes` and
exposes the stable read contract `weekly_neighborhood_asking_price_index` for backend queries.
See the [data-pipeline A07 contract](../data_pipeline/docs/neighborhood-price-index.md).

## Frontend geographic read views

The `frontend_geo_views_20261106` migration exposes `metro_stations` and `universities` as read-only views over
`geographic_reference_points`. Each view returns an ID, name, latitude, longitude,
coordinate provenance, confidence, source URL, and reference-registry version. The canonical
points are seeded or refreshed with `python -m data_pipeline.enrich_geography`; the
metro roster is the project's ten stations and the university set contains Yerevan
higher-education campuses represented in the data pipeline. Coordinates are approximate
campus markers. Frontend clients should receive these rows
through backend endpoints rather than connect directly to PostgreSQL.

The reference registry uses `yerevan-reference-v2`. Listing proximity features retain
`yerevan-geo-v1`, which uses the original four university campuses. These are separate
versioned contracts: a registry consumer must not infer that every published campus
participates in the existing nearest-university feature calculation.
