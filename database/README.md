# Database

Schema, migrations, observation history, and geographic data. Model listings and physical properties separately.

Stack: PostgreSQL, PostGIS, SQLAlchemy, and Alembic; hosted on AWS RDS. See the [technology stack](../docs/technology-stack.md).

A07 publishes weekly asking-price aggregates in `weekly_neighborhood_price_indexes` and
exposes the stable read contract `weekly_neighborhood_asking_price_index` for backend queries.
See the [data-pipeline A07 contract](../data_pipeline/docs/neighborhood-price-index.md).
