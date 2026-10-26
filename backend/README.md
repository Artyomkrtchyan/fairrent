# Backend

API, business rules, model integration, and review queue. Start with the API contract and a valuation stub.

C01: [OpenAPI, synthetic examples and validation](../contracts/README.md). Final owner agreement for the business API is pending. C02 provides the implemented local environment and health/readiness endpoints.

Stack: Python, FastAPI, Pydantic, SQLAlchemy, Alembic, and pytest. See the [technology stack](../docs/technology-stack.md).

C03 now implements listing search, details and bounded map queries. See
[C03 setup, source mapping and publication](../docs/C03-listing-api.md).
After A03/A04 ingestion finishes, run `docker compose exec api python -m sync_listings`
to publish its inventory atomically to the API read model. The command initializes
the projection and reports records excluded for missing evidence. Source tables
remain owned by the pipeline.

C06 implements `GET /api/v1/market-index` using A07's published weekly asking-price
view. See [C06 market analytics](../docs/C06-market-analytics.md) for setup, field
mapping, date coverage and integration tests.

## Local development with Docker Compose

C05 adds the protected reviewer queue, versioned decisions and revocable bearer
sessions. See [C05 setup and remaining integration work](../docs/C05-review-workflow.md).
Production signal generation awaits C04/B06; this foundation does not close C05.

Run these commands from the repository root. Docker Engine and Docker Compose are required.

Create local configuration on the first run:

```bash
cp .env.example .env
```

The example credentials are for local development only. Do not commit `.env`.

Build and start the API and PostgreSQL/PostGIS:

```bash
docker compose up --build -d
docker compose ps
```

Endpoints:

- http://localhost:8000/health — API process health.
- http://localhost:8000/ready — database connectivity; returns 503 when unavailable.
- http://localhost:8000/docs — interactive API documentation.

Inspect logs and stop services:

```bash
docker compose logs --tail=50 api db
docker compose down
```

Database data persists in the `postgres_data` volume after shutdown.
Database credentials in `.env` initialize a new database volume; changing them
does not update credentials in an existing database.

## Model stub

`model_stub.py` provides a temporary internal valuation stub:

```bash
docker compose exec api python -c 'from model_stub import assess; print(assess())'
```

It returns `insufficient_data` with null prices. It is not the complete C01
response or a valuation endpoint.

## Verification performed

- API and database containers become healthy.
- `/health` and `/ready` return 200 with the database available.
- Stopping the database makes `/ready` return 503 while `/health` remains 200.
- Restarting the database restores `/ready` to 200.
- PostGIS responds to `SELECT PostGIS_Version();`.
- The model stub can be imported and called inside the API container.

## Automated API tests

From the repository root, with a Python virtual environment activated:

```bash
python -m pip install -r backend/requirements-dev.txt
python -m pytest backend/tests -v
```

Tests cover `/health`, successful database readiness, and database connection
failure. Database connections are mocked; Docker and a running database are
not required. Real PostGIS connectivity is verified separately through Compose.
