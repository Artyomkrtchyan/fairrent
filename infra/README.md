# Infrastructure

Reproducible application setup, CI, weekly collection, and deployment. Add CI checks that perform meaningful validation.

C08 stack: ALB, EC2 Auto Scaling, Docker/Nginx, ECR, private RDS PostgreSQL/PostGIS, private S3 artifacts and CloudWatch. C09 prepares Linux cron on a designated collection host. Terraform manages infrastructure, GitHub Actions handles CI/CD, and Docker Compose supports local development. See the [technology stack](../docs/technology-stack.md).

C08 completion is documented in [the deployment evidence](../docs/C08-completion.md).
C09 prepares a dedicated-host Linux cron runner; see [setup, recovery and activation gates](../docs/C09-weekly-ingestion.md). No schedule is activated by the source files.
