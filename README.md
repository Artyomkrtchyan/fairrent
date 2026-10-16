# FairRent — Rental Housing Fair-Price Estimator

A four-person student project that estimates rental price ranges, explains valuation factors, and flags listings for review.

Status: planning. Application code and individual tasks have not been created yet.

Repository: https://github.com/Artyomkrtchyan/fairrent

Team board: https://github.com/users/Artyomkrtchyan/projects/4

Team roles: [Responsibilities and GitHub accounts](docs/team.md).

## User outcomes

- A searchable listing catalogue and map.
- Expected rental prices, estimated ranges, and explanations.
- Separate signals for price anomalies and potential risks.
- A manual review queue.
- Neighborhood asking-price indexes with update dates and observation counts.

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

1. [Scope and business rules](docs/business-rules.md).
2. [Team workflow, phases, and dependencies](docs/team-workflow.md).
3. [Initial data contract](docs/data-contract.md).
4. [GitHub Project setup](docs/github-setup.md).
5. [Contribution guidelines](CONTRIBUTING.md).

The city, sources, technology stack, and deadlines remain undecided. Three areas have assigned owners; the Backend/Automation/Deployment owner is awaiting confirmation. Record decisions in `docs/decisions.md`.

All repository documentation, issues, pull requests, comments, and commit messages must be written in English.
