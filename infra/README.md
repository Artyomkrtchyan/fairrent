# Infrastructure

Reproducible application setup, CI, weekly collection, and deployment. Add CI checks that perform meaningful validation.

## Owners and system administration lab

- @Artyomkrtchyan owns CI, Terraform, AWS deployment and scheduled ingestion (C tasks).
- @manemazmand (Mane) owns the System Administration Lab (S01–S04): an isolated Ubuntu VM, Linux access/permissions/firewall setup, Docker Compose operations, service diagnostics, synthetic database backup/restore and failure recovery.
- @alisamanukyann owns database schemas and migrations; coordinate restore compatibility with her.

See [lab scope and task sequence](../docs/system-administration.md). Put future lab scripts in `infra/lab/` and operational procedures in `docs/operations/`. The lab uses manual configuration and small shell scripts, requires no Ansible, and follows frontend MVP priorities. It does not block the AWS release.

Stack: AWS S3, CloudFront, ECS Fargate, ECR, RDS PostgreSQL/PostGIS, EventBridge Scheduler, and CloudWatch. Terraform manages infrastructure, GitHub Actions handles CI/CD, and Docker Compose supports local development. See the [technology stack](../docs/technology-stack.md).
