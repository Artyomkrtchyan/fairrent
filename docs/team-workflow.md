# Team workflow and implementation order

| Area | Owner | Deliverables |
| --- | --- | --- |
| A: Data + DB | [alisamanukyann](https://github.com/alisamanukyann) | Normalized data, database, price history, geographic features |
| B: ML + Ontology | [Lazr22](https://github.com/Lazr22) | Baseline, model, knowledge representation, evaluation |
| C: Backend + Automation + Deployment | [Artyomkrtchyan](https://github.com/Artyomkrtchyan) | API, risk rules, review queue, application setup |
| D: Frontend + UX + Analytics; S: System Administration | [manemazmand](https://github.com/manemazmand) | Catalogue, map, valuation interface, analytics; Linux environment, diagnostics, backup/restore and recovery |

## Phases

1. Together: agree on scope, sources, data, API, and synthetic examples.
2. In parallel: A prepares collection/database; B designs the ontology and baseline; C builds the API with a model stub; D builds the UI using mock responses.
3. End-to-end MVP: real listings from A → API from C → interface from D; integrate B's baseline through C.
4. Improvements: A expands and cleans data; B trains and evaluates the model; C adds the queue and scheduling; D adds the map and explanations.
5. Together: integration, quality evaluation, deployment, and demonstration.

## Dependencies

- B needs A's cleaned data for training but can start design immediately.
- C depends on A's schema and B's model interface; use stubs until they are ready.
- D depends on C's API contract; UI implementation can begin before the server is ready.
- A and B agree on features; C and D agree on requests, errors, filters, and pagination.
- Establish CI and reproducible setup early.

Hold a short weekly integration demonstration, review blockers, and update the board. The [implementation plan](implementation-plan.md) defines all 41 assigned tasks and their dependencies.
