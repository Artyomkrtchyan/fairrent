# FairRent — Rental Housing Fair-Price Estimator

A four-person student project that estimates rental price ranges, explains valuation factors, and flags listings for review.

Repository: https://github.com/Artyomkrtchyan/fairrent

Team board: https://github.com/users/Artyomkrtchyan/projects/4

Team roles: [Responsibilities and GitHub accounts](docs/team.md).

Mane also owns an isolated [system administration learning track](docs/system-administration.md): Linux setup, diagnostics, backup/restore and recovery. It requires no Ansible and does not change the AWS production architecture.

## Technology stack

React, TypeScript, Vite, Leaflet, and Recharts for the frontend; Python, FastAPI, and Pydantic for the backend; PostgreSQL/PostGIS with SQLAlchemy and Alembic for data storage; pandas, scikit-learn, and CatBoost for ML; Protégé, OWL/RDF, and RDFLib for knowledge engineering.

AWS hosting with Terraform, Docker, and GitHub Actions. See the [complete technology stack and architecture](docs/technology-stack.md).

## User outcomes

- A searchable listing catalogue and map.
- Expected rental prices, estimated ranges, and explanations.
- Separate signals for price anomalies and potential risks.
- A manual review queue.
- Neighborhood asking-price indexes with update dates and observation counts.
- Coordinate-based rental assessments and local price standard deviations from a Pandas/Scikit-Learn analysis pipeline.
- A weekly cron workflow for listing collection, obsolete active-inventory cleanup, and outlier review queue processing.

A high price does not prove fraud. The system provides signals for review.

## Repository structure

| Directory | Responsibility |
| --- | --- |
| `data_pipeline/` | Collection, cleaning, normalization, deduplication |
| `database/` | Database schema, migrations, geographic data |
| `ml/` | Baseline estimator, model, evaluation |
| `ontology/` | Entities, relationships, inference rules |
| `backend/` | API, business workflows, review queue |
| `frontend/` | Catalogue, map, analytics, review interface |
| `infra/` | Application setup, automation, deployment |
| `docs/` | Requirements, contracts, team workflow |

## Start here

See the [implementation plan and task dependencies](docs/implementation-plan.md).

1. [Scope and business rules](docs/business-rules.md).
2. [Team workflow, phases, and dependencies](docs/team-workflow.md).
3. [Initial data contract](docs/data-contract.md).
4. [GitHub Project setup](docs/github-setup.md).
5. [Contribution guidelines](CONTRIBUTING.md).
6. [Git branches, commits, push, and pull requests](docs/git-workflow.md).
