# Team workflow and implementation order

| Area | Owner | Deliverables |
| --- | --- | --- |
| A: Data + DB | [alisamanukyann](https://github.com/alisamanukyann) | Normalized data, database, price history, geographic features |
| B: ML + Ontology | [Lazr22](https://github.com/Lazr22) | Baseline, model, knowledge representation, evaluation |
| C: Backend + Automation + Deployment | [Artyomkrtchyan](https://github.com/Artyomkrtchyan) | API, risk rules, review queue, application setup |
| D: Frontend + UX + Analytics; E: Application Security; S: System Administration | [manemazmand](https://github.com/manemazmand) | Catalogue, map, valuations and analytics; risk assessment, security checks and incident response; optional administration after release |

## Phases

1. Together: agree on scope, sources, data, API, and synthetic examples.
2. In parallel: A prepares collection/database; B designs the ontology and baseline; C builds the API with a model stub; D builds the UI using mock responses.
3. End-to-end MVP: real listings from A → API from C → interface from D; integrate B's baseline through C.
4. Improvements: A expands and cleans data; B trains and evaluates the model; C adds the queue and scheduling; D adds the map and explanations.
5. Together: integration, quality evaluation, deployment, security verification (E05), and demonstration.
6. After core release and security completion: S01–S04, only if time remains.

## Dependencies

- B needs A's cleaned data for training but can start design immediately.
- C depends on A's schema and B's model interface; use stubs until they are ready.
- D depends on C's API contract; UI implementation can begin before the server is ready.
- A and B agree on features; C and D agree on requests, errors, filters, and pagination.
- Establish CI and reproducible setup early.
- E01 starts independently; E02 follows C02, E03 follows reviewer integration, E04 follows deployment and artifact delivery, and E05 feeds C10. E tasks never depend on optional S tasks.
- AWS resources, Terraform and IAM are Artyom's responsibility. Mane verifies application controls and reports infrastructure observations to him.

## Course topics applied to project tasks

The supplied Information and Cyber Security syllabus (academic year 2024–2025) informs practical acceptance criteria; the tasks remain normal project work.

| Syllabus topic | Project application |
| --- | --- |
| 1–3: CIA, security frameworks, asset classification and ownership | E01 asset inventory, risk register and selected NIST CSF/CIS control mapping |
| 4: Risk lifecycle, STRIDE, audit and incident analysis | E01 threat model and residual risk; E05 scoped assessment and incident runbook |
| 5: Hashing, PKI and OpenSSL | E04 trusted artifact integrity checks and HTTPS certificate validation |
| 6: Network security and access control | E03 reviewer authorization; E04 verification of service exposure; AWS IAM remains with Artyom |
| 7: Ethical testing and emerging threats | E02 vulnerability checks; E03/E05 authorized testing; E04 model-artifact handling |

Project-specific additions include CI secret/dependency/container checks, browser session and injection tests, request limits and safe logging. No separate email-cryptography, IoT or blockchain implementation is required because FairRent has no such component. No framework certification is claimed.

Hold a short weekly integration demonstration, review blockers, and update the board. The [implementation plan](implementation-plan.md) defines all 46 assigned tasks and their dependencies.
