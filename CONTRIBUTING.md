# Contributing

- Give each task one owner and use a short-lived branch from the latest `main`.
- Branch names: `feat/<topic>`, `fix/<topic>`, `docs/<topic>`, `chore/<topic>`.
- Submit changes through a pull request reviewed by at least one other teammate.
- Include the purpose, linked issue, validation steps, and limitations in each PR.
- Agree on data/API contract changes with consuming components before implementation.
- Each member maintains documentation and appropriate checks for their components.
- Do not commit secrets, personal data, raw data exports, or large model files.
- Small synthetic examples are welcome; document the provenance of real data separately.

## System administration contributions

Mane (@manemazmand) owns frontend/analytics and the S01–S04 System Administration Lab. See [team responsibilities](docs/team.md) and [lab scope](docs/system-administration.md). Lab changes include manual Linux setup, diagnostic shell scripts, synthetic database backup/restore and recovery instructions; no Ansible is required. Keep scripts in `infra/lab/` and procedures in `docs/operations/` when implementing those tasks. Include sanitized verification evidence, and keep VM images, private keys, environment secrets and database dumps out of Git. Coordinate database changes with Alisa and production infrastructure changes with Artyom.

## Definition of Ready

A task has a goal, scope, deliverables, dependencies, and acceptance criteria.

## Definition of Done

Acceptance criteria are met, appropriate checks pass, documentation is current, another teammate has reviewed the PR, and integration with adjacent components has been verified where applicable.
