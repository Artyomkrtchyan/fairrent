# Technology stack

The team's current stack for FairRent.

| Area | Technologies | Purpose |
| --- | --- | --- |
| Frontend | React + TypeScript + Vite | Listing catalogue, filters, property details, and review interface |
| Maps & Charts | Leaflet + Recharts | Property and infrastructure maps, neighborhood price trends |
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
