# Technology stack

The team's current stack for FairRent.

| Area | Technologies | Purpose |
| --- | --- | --- |
| Frontend | React + TypeScript + Vite | Listing catalogue, filters, property details, and review interface |
| Maps & Charts | MapLibre GL JS + Recharts | Map-first property exploration, 2D/3D building views and neighborhood price trends |
| Backend | Python + FastAPI + Pydantic | REST API, business logic, data validation, and OpenAPI documentation |
| Database | PostgreSQL + PostGIS | Listings, price history, neighborhoods, and geographic queries |
| Database Access & Migrations | SQLAlchemy + Alembic | Data models, database access, and versioned schema migrations |
| Data Collection | Python + HTTPX + BeautifulSoup | Fetching and parsing listings; add Playwright if JavaScript rendering is required |
| Machine Learning | pandas + scikit-learn + CatBoost | Data preparation, baseline estimation, rental price prediction, and model evaluation |
| Knowledge Engineering | Protégé + OWL/RDF + RDFLib | Real estate ontology, relationships, and explainable inference rules |
| Testing | pytest + Playwright | Backend tests, rule validation, and end-to-end user scenarios |
| Frontend Hosting | AWS S3 + CloudFront | Hosting and delivering the frontend |
| Backend Hosting | AWS ECS Fargate + ECR | Running Docker containers and storing container images |
| Managed Database | AWS RDS PostgreSQL + PostGIS | Hosting relational and geographic data |
| Data & Model Storage | AWS S3 | Storing datasets, model artifacts, and evaluation outputs |
| Scheduled Jobs | EventBridge Scheduler cron + ECS Tasks | Weekly listing collection and processing |
| Logging | AWS CloudWatch | Application logs and scheduled job monitoring |
| Infrastructure as Code | Terraform | Reproducible AWS infrastructure provisioning |
| CI/CD | GitHub Actions | Automated checks, container builds, and deployment |
| Local Development | Docker + Docker Compose | Consistent local environments for all team members |
| Application Security | Threat modelling, secret/dependency/image checks, API security tests, OpenSSL and artifact checksums | Risk assessment, security verification and incident response |
| System Administration | Ubuntu Linux VM, SSH, shell scripts, Docker Compose, PostgreSQL backup/restore tools | Environment configuration, diagnostics and recovery |

## Component boundaries

- The frontend calls the FastAPI backend.
- The backend reads PostgreSQL/PostGIS and invokes the valuation model within the application.
- A separate collection process normalizes listings and writes observations to the database.
- EventBridge Scheduler starts the collection process as an ECS task each week.
- The coordinate valuation endpoint returns local sample standard deviations and valuation assessments from the Pandas/Scikit-Learn pipeline; CatBoost is the candidate price model.
- The manual review queue is stored in PostgreSQL.
- S3 stores datasets and model artifacts; ECR stores container images.
- Terraform defines AWS resources; GitHub Actions runs checks and deployment workflows.

Docker Compose provides the local development environment. AWS resources are provisioned during deployment; this document records the architecture and does not indicate that infrastructure is already deployed.


## Mapping direction — agreed 2026-10-22

MapLibre GL JS replaces the previously planned 2D map library. D05 will implement
a framed map introduction below the header, with an explicit full-screen action,
easy scrolling to filters, price markers, and linked property previews.
Users can switch between a flat 2D view and a tilted 3D building view. Recharts
remains the charting library; React, TypeScript, Vite and AWS hosting are unchanged.

The renderer is separate from its data provider. D05 must select a compatible
vector-tile/style provider and verify Yerevan building footprints and available
height attributes, licensing, attribution, browser-visible key restrictions and
costs before enabling external services. A 3D view uses building extrusions where
suitable data exists, not automatically photorealistic buildings. Unsupported
areas/devices need a usable 2D/list fallback; do not fabricate building heights.

A colorful gradient layer must represent a defined rental measure, such as
median asking rent per m², with units, legend, sample counts and source freshness.
Sparse or unavailable areas stay neutral. Any interpolation needs an agreed
method and must not imply measured values where none exist. Authoritative
aggregates depend on A07/C06; this layer is not provided by changing renderers.

This records the target design and technology choice, not an installed map,
selected provider, deployed feature or new C01 endpoint. See the D05 criteria and
[D01 design revision](design/D01-screen-contracts.md#map-first-revision--agreed-2026-10-22).


### Map presentation refinement — agreed 2026-10-24

The embedded opening map is framed within a navy introduction, rather than
occupying the whole viewport. A short headline, Explore Yerevan toolbar and
Browse rentals actions connect it to the filters below. Expand map opens a
separate full-screen modal; ordinary map clicks do not. Embedded wheel scrolling
continues down the page. This supersedes the earlier viewport-filling default,
while retaining the MapLibre renderer and D05's remaining data/3D requirements.
