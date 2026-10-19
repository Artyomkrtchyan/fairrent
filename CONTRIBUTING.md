# Contributing

- Give each task one owner and use a short-lived branch from the latest `main`.
- Branch names: `feat/<topic>`, `fix/<topic>`, `docs/<topic>`, `chore/<topic>`.
- Submit changes through a pull request reviewed by at least one other teammate.
- Include the purpose, linked issue, validation steps, and limitations in each PR.
- Agree on data/API contract changes with consuming components before implementation.
- Each member maintains documentation and appropriate checks for their components.
- Do not commit secrets, personal data, raw data exports, or large model files.
- Small synthetic examples are welcome; document the provenance of real data separately.
- Security changes include a reproducible finding, impact, fix and retest evidence. Test only owned environments within an agreed scope and avoid secrets or sensitive data in logs and reports.

## Definition of Ready

A task has a goal, scope, deliverables, dependencies, and acceptance criteria.

## Definition of Done

Acceptance criteria are met, appropriate checks pass, documentation is current, another teammate has reviewed the PR, and integration with adjacent components has been verified where applicable.
