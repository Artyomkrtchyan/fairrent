# GitHub setup

## Completed on October 16, 2026

- Private repository: https://github.com/Artyomkrtchyan/fairrent
- Linked private project: https://github.com/users/Artyomkrtchyan/projects/4
- Initial documentation, module structure, and templates pushed to main.
- Board: Backlog → Ready → In Progress → Review → Done.
- Planning: table with assignees, status, Area, Priority, and Phase.
- Area: Data / DB, ML / Ontology, Backend, Frontend, Infra, Docs / QA.
- Priority: P0, P1, P2. Phase: Foundation, MVP, Intelligence, Release.
- fairrent selected as the default repository for new project issues.
- Repository invitations sent to alisamanukyann, Lazr22, and manemazmand.
- All three teammates granted Write access to the project board.
- All four area owners documented in [team responsibilities](team.md).

Repository name: `fairrent`. Visibility: private.

## Task board completed on October 17, 2026

- 37 repository issues created and linked to the project, with acceptance criteria and issue dependency links.
- Data/DB: 8 tasks assigned to alisamanukyann.
- ML/Knowledge Engineering: 9 tasks assigned to Lazr22.
- Backend/Automation/Deployment: 11 tasks assigned to Artyomkrtchyan.
- Frontend/Analytics: 9 tasks assigned to manemazmand.
- Area, Priority, and Phase populated for all cards; independent starting tasks initially set to Ready and dependent work to Backlog.
- See the [implementation plan](implementation-plan.md) and [Git workflow](git-workflow.md).

## Additional tasks assigned October 17, 2026

- S01–S04 created as issues #40–43, assigned to manemazmand and added to project 4.
- S01–S04 are now Backlog / Infra / P2 / Release, after the core release and security tasks, only if time remains.
- The plan has 46 tasks. Mane owns nine frontend tasks, five application security tasks (E01–E05) and four optional operations tasks (S01–S04).
- S01–S04 cover Linux configuration, access, monitoring, database backup/restore and service recovery. Acceptance criteria and dependencies follow the same format as the other tasks.
- E01–E05 cover assets/risks, security CI and container review, application access/input tests, transport/artifact verification and incident response. AWS and IAM remain owned by Artyom. E05 is a dependency of C10; S tasks do not block release.
- E01–E05 are issues #47–51, assigned to manemazmand and included in project 4. E01–E02 are Ready; E03–E05 remain Backlog until dependencies are complete. All are P0; phases follow the implementation plan.
- Regenerate task documents with `python docs/generate-task-docs.py`. `board-tasks.json` is the task definition source and `board-issues.json` maps codes to actual GitHub issues. Updating GitHub with `docs/sync-mane-tasks.py` requires an authenticated CLI; Projects fields are maintained separately.

## Remaining configuration (unchanged)

- Optional By Area view grouped by responsibility.
- Track dependencies using linked issues; a custom Depends on field has not been created.
- Suggested labels: area:data, area:db, area:ml, area:ontology, area:backend, area:frontend, area:infra, area:docs, type:feature, type:bug, type:research, blocked.
- Suggested milestones: Foundation, End-to-end MVP, Model and Ontology, Release and Demo. Set dates with the team.
- Proposed main protection: require pull requests, one independent review, and resolved conversations. Add required CI checks when meaningful checks exist. Protection availability depends on the GitHub plan and repository visibility.

The By Area view, suggested labels, milestones, and main protection have not been configured. Do not mark settings complete without verifying them on GitHub.
