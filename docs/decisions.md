# Team decisions

| Question | Status | Decision |
| --- | --- | --- |
| City | Confirmed | Yerevan, Armenia |
| Reporting currency | Confirmed | USD; preserve original listing amounts and currencies |
| Listing source | Confirmed | list.am |
| Hosting | Confirmed | AWS |
| Infrastructure and delivery | Confirmed | Terraform, Docker, GitHub Actions |
| Coordinate valuation outcome | Confirmed | Pandas/Scikit-Learn pipeline and a REST endpoint returning local price standard deviations and valuation assessments for supplied coordinates |
| Weekly orchestration | Confirmed | Cron workflow harvests listings, clears obsolete active inventory, refreshes valuations, and enqueues outliers for review |
| Application and platform stack | Adopted | See [technology stack](technology-stack.md) for the current component choices and architecture |
| Team and area owners | Confirmed | Data/DB: alisamanukyann; ML/Knowledge Engineering: Lazr22; Frontend/Analytics and System Administration Lab: manemazmand; Backend/Automation/Deployment: Artyomkrtchyan |
| System administration learning track | Adopted | Mane owns S01–S04: isolated Linux VM, access configuration, diagnostics, backup/restore and failure recovery. Manual setup and shell scripts; no Ansible. Schedule around frontend MVP priorities. See [scope and responsibility boundaries](system-administration.md). |
