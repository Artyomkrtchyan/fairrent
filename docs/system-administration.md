# System administration learning track

Owner: @manemazmand. Existing frontend tasks D01–D09 remain assigned to Mane.
This track adds Linux operations practice; it does not transfer AWS deployment
ownership from @Artyomkrtchyan or database schema ownership from @alisamanukyann.

## Scope and sequence

| Task | Deliverable | Depends on |
| --- | --- | --- |
| S01 | Clean Ubuntu VM, administrator/SSH/firewall setup, manual Compose deployment guide | C02 |
| S02 | Host/service diagnostic checklist, health-check shell script and log retention | S01 |
| S03 | Synthetic database backup and verified restore into a separate disposable target | S01 |
| S04 | Failure/recovery exercises and a teammate-tested administration runbook | S02, S03 |

Use an isolated local VM and synthetic data. Do not publish credentials, SSH keys,
VM disks or database dumps. Store eventual operational scripts under `infra/lab/`
and procedures under `docs/operations/`; these implementations belong to S tasks.
No Ansible is required. Small shell scripts may automate repetitive checks.
This planning change does not create a VM or provision paid resources.

S01 starts after C02 is integrated. Complete frontend MVP priorities first, then
take one S task at a time. S02 and S03 have equal dependency readiness but are not
an expectation of simultaneous work. S04 is a learning-track milestone and does
not block the application release or C08/C10.

## Responsibility boundaries

- Mane operates the lab, documents access/networking/storage, verifies backups and investigates failures.
- Alisa owns schemas, migrations and data semantics; Mane coordinates restore compatibility with her.
- Artyom owns application integration, Terraform, AWS deployment, CI and scheduled ingestion.
- Production logs/monitoring and RDS backup responsibilities remain in C08/C09; lab findings may inform those tasks without replacing them.

Acceptance requires reproducible evidence, not only documentation. A restored
synthetic dataset and recovery after a controlled failure are the main demo
artifacts. Detailed criteria are in the implementation plan and GitHub issues.
