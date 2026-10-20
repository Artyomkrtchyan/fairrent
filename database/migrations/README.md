## Database & Migrations

This project uses **PostgreSQL** with the **PostGIS** extension enabled, managed via **SQLAlchemy (ORM)** and **Alembic** for schema migrations.

### Prerequisites
* PostgreSQL installed locally (or via Docker).
* Python environment with required dependencies installed (`sqlalchemy`, `geoalchemy2`, `alembic`, `psycopg`).

### 1. Database Setup
Create the PostgreSQL database and enable the PostGIS extension:
CREATE DATABASE fairrent;
\c fairrent;
CREATE EXTENSION IF NOT EXISTS postgis;Generic single-database configuration.

### 2. Configuration
Ensure your database/alembic.ini file points to your correct database URL:
sqlalchemy.url = postgresql://postgres:your_password@localhost:5432/fairrent


### 3. Running Migrations
To apply the latest database schema and spatial tables, navigate to the database/ directory and run:
cd database
python -m alembic upgrade head
