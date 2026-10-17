# Infrastructure

Reproducible application setup, CI, weekly collection, and deployment. Add CI checks that perform meaningful validation.

## Responsibilities

- @Artyomkrtchyan owns CI coordination, Terraform, AWS deployment, IAM and scheduled ingestion (C tasks).
- @manemazmand (Mane) owns application security checks, container review and incident procedures (E01–E05), coordinating workflow changes with Artyom. Environment configuration, monitoring, backup/restore and recovery (S01–S04) follow the core release and security tasks, only if time remains.
- @alisamanukyann owns database schemas and migrations; coordinate restore compatibility with her.

See the [implementation plan](../docs/implementation-plan.md) for tasks and dependencies. Store operational scripts in `infra/operations/` and procedures in `docs/operations/`.

Stack: AWS S3, CloudFront, ECS Fargate, ECR, RDS PostgreSQL/PostGIS, EventBridge Scheduler, and CloudWatch. Terraform manages infrastructure, GitHub Actions handles CI/CD, and Docker Compose supports local development. See the [technology stack](../docs/technology-stack.md).
