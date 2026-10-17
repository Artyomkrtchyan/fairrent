# Team responsibilities

| Area | GitHub account | Responsibilities | Deliverables |
| --- | --- | --- | --- |
| Data Engineering & Database | [alisamanukyann](https://github.com/alisamanukyann) | Collect, clean and normalize listings; detect duplicates; design the database; maintain price history; enrich geographic data. | Collection pipeline, database schema, cleaned dataset, geographic features and historical records. |
| Machine Learning & Knowledge Engineering | [Lazr22](https://github.com/Lazr22) | Define the real estate ontology; build baseline and ML estimators; estimate price ranges; explain factors; evaluate quality. | Ontology, inference rules, baseline, trained model, prediction intervals and evaluation report. |
| Frontend, Analytics & System Administration Lab | [manemazmand](https://github.com/manemazmand) | Build the frontend; operate an isolated Linux lab, diagnose services, verify backups and recovery. | Web interface, map, charts, review dashboard; Linux setup guide, monitoring checks, restore evidence and administration runbook (S01–S04). |
| Backend, Automation & Deployment | [Artyomkrtchyan](https://github.com/Artyomkrtchyan) | Develop APIs; integrate database and model; implement risk rules and review workflow; schedule jobs; manage deployment. | API, integration, risk signals, review queue, scheduled jobs and deployment configuration. |

Each member tests and documents their components. Data/API contracts and integration checks are shared responsibilities. See the [implementation plan](implementation-plan.md) for individual tasks and dependencies.

Mane's [system administration track](system-administration.md) is scheduled sequentially around frontend MVP work. It uses a local VM and requires no Ansible. AWS deployment remains owned by Artyom; database schema ownership remains with Alisa.
