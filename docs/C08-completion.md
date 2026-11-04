# C08 deployment completion

Verified environment: `fairrent.online`, account 566663271715, eu-central-1.
The accepted architecture is HTTPS ALB -> EC2 Auto Scaling -> Nginx/React +
FastAPI, with private RDS/PostGIS and immutable ECR images. This replaces the
original ECS and S3/CloudFront frontend plan; S3 is private artifact storage.

## Cost assumptions recorded before provisioning

The additional Terraform plan creates a separate artifact bucket, two CloudWatch
log groups and a scoped EC2 role policy. It adds no EC2, RDS, ALB or NAT capacity.
Assume 1 GB total S3 Standard artifacts INCLUDING retained versions, 1 GB/month
custom log ingestion, and 0.5 GB-month retained log storage with 14-day retention.
Official Frankfurt regional catalogs checked on 2026-11-04 give:

- S3 Standard: $0.0245/GB-month for the first 50 TB.
- CloudWatch custom Standard ingestion: $0.63/GB.
- CloudWatch retained logs: $0.0324/GB-month.

This example adds about $0.67/month before requests, transfer and taxes; it is a
usage assumption, not a billing cap. Larger artifacts, old object versions and
more logs increase cost. Existing EC2/RDS/ALB/EBS/public IPv4/ECR/Secrets Manager
charges continue. There is no production HA claim: one t3.small ASG instance,
one db.t3.micro RDS instance, 20 GB gp3 and one-day automated DB backups are the
development baseline. Temporary rolling replacement can run two EC2 instances.

Sources: [S3 regional catalog](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonS3/current/eu-central-1/index.json),
[CloudWatch regional catalog](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonCloudWatch/current/eu-central-1/index.json).

## Storage and logging

Artifacts use `fairrent-artifacts-566663271715-eu-central-1`, separate from the
Terraform state bucket `fair-rent-s5`. Public access and ACLs are blocked, HTTPS
is mandatory, AES256 encryption and versioning are enabled. Terraform prevents
bucket destruction and does not force-delete object versions. EC2 can read only
`models/`; it cannot read Terraform state or write/delete model objects through
this policy. Release operators upload a package under a new immutable version
prefix, retain SHA256SUMS.json, and record the S3 VersionIds. B07 validates its
checksums when loading. No synthetic test model is installed as production data.

Container stdout/stderr goes to `/fairrent/dev/backend` and
`/fairrent/dev/frontend`. Terraform owns the groups and their 14-day retention;
EC2 can create streams and publish events only in these groups. Docker uses its
instance role, without static AWS keys, and a bounded nonblocking buffer so log
service delays cannot block API requests. Golden-AMI systemd supervision remains;
release user data installs the reviewed bootstrap scripts and enables log-group
settings before restarting services. User data is checked against EC2's 16 KiB
limit before creating a launch-template version.

## Verification evidence and release gate

The 2026-11-04 audit confirmed the HTTP->HTTPS redirect, valid ACM certificate,
HTTPS site/health/readiness/catalog responses and reviewer 401 without a token.
RDS is private and encrypted; its only 5432 ingress comes from the backend SG.
The active ASG release completed with 100% healthy minimum capacity, 200% maximum
replacement capacity, 180-second warmup and AutoRollback=true. Both ECR repositories
use immutable tags and scan-on-push. Credentials come from Secrets Manager via
an EC2 role and a root-only temporary PGPASSFILE, never Docker PGPASSWORD metadata.
The owner explicitly retained public SSH/22 on 2026-11-04; this change preserves it.
Database TLS is encrypted with sslmode=require; hostname/CA validation is tracked
under E04. This is a development deployment, not full production hardening.

After the completion PR is merged, verify the new release reaches healthy targets,
create a uniquely tagged /health request and confirm it appears in both log groups.
Verify artifact versioning/encryption/public denial with a synthetic smoke object,
then remove only that object's test version. Record these results in the issue.
The API image includes public municipal coverage so coordinate valuation can run
without a host checkout; Compose may still override coverage with read-only mounts.

## Migration, rollback and teardown

Migrations remain a separate operator step before switching incompatible API code:
initialize the C03 projection, apply `python -m valuation_repository` and
`python -m reviewer_auth migrate` as required by the release. Back up RDS first;
never automatically downgrade schemas during an application rollback. C09 owns
scheduled ingestion; C10 owns the full collection-to-reviewer demo.

Normal rollback is a reviewed revert PR to main, which creates a new digest-based
rolling release. For urgent recovery select the previous numbered launch-template
version and start an ASG refresh; retain its AMI and ECR digests. Current and previous
numbered versions are printed in the workflow summary. AutoRollback uses ALB health,
so it complements rather than replaces functional checks. Do not deliberately
break or roll back the live service merely to test the runbook.

Before teardown set AWS_DEPLOY_ENABLED=false, stop future C09 schedules and take
an explicit final DB snapshot/export. Current development Terraform has
skip_final_snapshot=true and deletes automated backups: do not run destroy until
retention is explicitly decided. Keep the Terraform state bucket. Artifact
prevent_destroy intentionally blocks full destruction; remove it only through a
reviewed retention decision after backing up and handling object versions. Inspect
the complete destroy plan and obtain authorization before deleting data. Never
use a broad S3 recursive delete as an implicit teardown step.


Terraform applied the reviewed saved plan on 2026-11-04: **9 added, 0 changed,
0 destroyed**. Offline Linux verification passed **14 tests and 4 subtests**,
covering credential redaction, pull-failure preservation, CloudWatch configuration,
release config preservation and the EC2 user-data size limit (12,029 bytes).
Final CloudWatch delivery is a post-merge release check; do not mark it verified
until unique smoke requests are observed in both groups.
