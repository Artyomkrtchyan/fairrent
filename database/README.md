# Database

Schema, migrations, observation history, and geographic data. Model listings and physical properties separately.

Schema and migration owner: @alisamanukyann. Mane (@manemazmand) owns synthetic database backup/restore drills in the isolated System Administration Lab (S03), coordinating version and migration compatibility with the database owner. See [administration scope](../docs/system-administration.md); production RDS backup design remains part of C08.

Stack: PostgreSQL, PostGIS, SQLAlchemy, and Alembic; hosted on AWS RDS. See the [technology stack](../docs/technology-stack.md).
