# Database

Schema, migrations, observation history, and geographic data. Model listings and physical properties separately.

Schema and migration owner: @alisamanukyann. Mane (@manemazmand) owns backup/restore procedures and recovery verification (S03), coordinating database and migration compatibility with Alisa and deployment configuration with Artyom. See the [implementation plan](../docs/implementation-plan.md#s03).

Stack: PostgreSQL, PostGIS, SQLAlchemy, and Alembic; hosted on AWS RDS. See the [technology stack](../docs/technology-stack.md).
