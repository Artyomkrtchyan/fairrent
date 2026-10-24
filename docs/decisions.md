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
| Team and area owners | Confirmed | See [team responsibilities](team.md). |
| Optional system administration | Adopted | S01–S04 are Release/P2 and start after C10 and E05, only if time remains; they do not block the core release. |
| Map renderer and opening layout | Agreed 2026-10-22 | Mane reports Artyom's agreement to replace the planned map renderer with MapLibre GL JS. Browse will open on a viewport-filling map with compact filters, linked listings and 2D/3D mode. Provider, data coverage and cost validation remain D05 work; meaningful rental color layers require suitable aggregate data. See [mapping direction](technology-stack.md#mapping-direction--agreed-2026-10-22). |
| Map presentation refinement | Agreed 2026-10-24 | Opening map uses a rounded frame within the navy introduction, with filters below and explicit full-screen mode. This supersedes the earlier viewport-filling default; normal scrolling and Close/Escape return behavior are required. See [design refinement](design/D01-screen-contracts.md#framed-map-revision--agreed-2026-10-24). |

- 2026-10-24: D05 visual review uses a labelled mock-only synthetic monthly asking-rent-per-m² surface (green → yellow/orange → red). The gradient remains visible; toolbar Search this area adds apartment dots and updates the catalogue, clearing bbox hides dots. This metric is distinct from listing asking-vs-estimate comparison. Real rendering still requires an agreed aggregate source, coverage/counts/freshness; synthetic colours never replace failed real data.
