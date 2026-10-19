# GitHub project setup

- Repository: [Artyomkrtchyan/fairrent](https://github.com/Artyomkrtchyan/fairrent) (private).
- Project: [FairRent — Team Board](https://github.com/users/Artyomkrtchyan/projects/4).
- Views: Board and Planning.
- Statuses: Backlog, Ready, In Progress, Waiting, Review, Done.
- Areas: Data / DB, ML / Ontology, Backend, Frontend, Infra, Docs / QA.
- Priorities: P0, P1, P2.
- Phases: Foundation, MVP, Intelligence, Release.

## Tasks

The [implementation plan](implementation-plan.md) contains 46 tasks with owners,
dependencies and acceptance criteria. [board-tasks.json](board-tasks.json) stores
task definitions; [board-issues.json](board-issues.json) maps task codes to GitHub issues.

Keep these documents and the project board consistent when changing task scope,
ownership or dependencies. Link blocking issues in issue descriptions. Move a task
to Ready only when its dependencies and scope are agreed.

## Pull requests and checks

Follow the [Git workflow](git-workflow.md). Backend tests and Docker image builds
run through GitHub Actions. Add component checks as implementations become available.

Branch protection is not configured. Availability for this private repository
depends on the GitHub plan. Do not describe checks as enforced merge requirements
unless repository settings confirm that they are required.
