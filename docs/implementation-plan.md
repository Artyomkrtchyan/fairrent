# Implementation plan

Each task has one owner, a goal, deliverables, dependencies and acceptance criteria. Dates are set by the team.

## Delivery sequence

Foundation → working baseline and coordinate-valuation MVP → model/ontology and analytics integration → deployment, security verification and demonstration.

Start A01, B01, C01, D01 and E01 independently. C01 establishes the shared contract. B09, C11 and D09 cover coordinate valuation and observed price dispersion; C09 covers weekly ingestion.

Security verification E05 feeds release verification C10. S01–S04 are optional Release/P2 tasks after the core release, only if time remains; they do not block C10.

<a id="a01"></a>

## A01: Inspect list.am listings and define the source mapping

Owner: @alisamanukyann | Area: Data / DB | Phase: Foundation | Priority: P0

Analyze Yerevan long-term apartment listings and map available source fields to the shared data contract.

Dependencies: None.

Acceptance criteria:

- [ ] Document available fields, missing values, pagination, and source update behavior.
- [ ] Provide a small sanitized or synthetic parser fixture and field mapping.
- [ ] Document collection constraints, rate limits, and a reproducible fallback import if access fails.

<a id="a02"></a>

## A02: Implement the PostgreSQL/PostGIS schema and migrations

Owner: @alisamanukyann | Area: Data / DB | Phase: Foundation | Priority: P0

Design and implement storage for properties, listings, observations, infrastructure, estimates, signals, reviews, and ingestion runs.

Dependencies: [A01](#a01), [C01](#c01)

Acceptance criteria:

- [ ] Publish an ER diagram and Alembic migrations that work on an empty database.
- [ ] Preserve source identity and price history with suitable constraints and geographic indexes.
- [ ] Provide synthetic seed data and coordinate schema ownership with backend.

<a id="a03"></a>

## A03: Build the listing collection and normalization pipeline

Owner: @alisamanukyann | Area: Data / DB | Phase: MVP | Priority: P0

Collect the selected list.am segment and normalize records for the Yerevan rental market.

Dependencies: [A01](#a01), [A02](#a02), [C02](#c02)

Acceptance criteria:

- [ ] Provide a repeatable CLI with bounded retries, pagination, and run summaries.
- [ ] Normalize monthly USD amounts while preserving original currencies, conversion provenance, and utility-cost uncertainty.
- [ ] Quarantine invalid records and test representative parsing and normalization failures.

<a id="a04"></a>

## A04: Handle duplicates, observations, and listing lifecycle

Owner: @alisamanukyann | Area: Data / DB | Phase: MVP | Priority: P0

Make repeated collection safe and keep inactive inventory distinguishable from collection failures.

Dependencies: [A03](#a03)

Acceptance criteria:

- [ ] Repeated runs do not duplicate listings or observations; price changes remain traceable.
- [ ] Document and verify duplicate grouping without merging unrelated properties.
- [ ] Deactivate records only after successful source observations under a documented staleness policy.

<a id="a05"></a>

## A05: Add Yerevan districts and infrastructure proximity features

Owner: @alisamanukyann | Area: Data / DB | Phase: MVP | Priority: P0

Enrich listings with districts, coordinates, and distances to metro stations, universities, and a defined city-center reference.

Dependencies: [A02](#a02), [A03](#a03)

Acceptance criteria:

- [ ] Record geographic data provenance and coordinate confidence; flag unresolved locations.
- [ ] Produce distance features with explicit units and a documented center definition.
- [ ] Validate known location examples and make the features available to ML and API consumers.

<a id="a06"></a>

## A06: Publish reproducible training and evaluation datasets

Owner: @alisamanukyann | Area: Data / DB | Phase: Intelligence | Priority: P0

Export versioned datasets following the feature contract and leakage-prevention rules.

Dependencies: [A04](#a04), [A05](#a05), [B02](#b02)

Acceptance criteria:

- [ ] Export includes observation dates, duplicate groups, feature definitions, and provenance.
- [ ] Provide a data-quality report covering missingness, invalid values, duplicates, and neighborhood coverage.
- [ ] Demonstrate reproducible snapshot generation without committing raw listings or personal data.

<a id="a07"></a>

## A07: Build neighborhood asking-price index aggregates

Owner: @alisamanukyann | Area: Data / DB | Phase: Intelligence | Priority: P1

Produce weekly neighborhood asking-price statistics for comparable active inventory.

Dependencies: [A04](#a04), [A05](#a05)

Acceptance criteria:

- [ ] Provide median USD/month and USD/m², sample counts, period, and data freshness.
- [ ] Define sparse-neighborhood behavior and avoid presenting listing prices as signed-contract prices.
- [ ] Validate aggregates against a small known dataset and expose a stable query interface to backend.

<a id="a08"></a>

## A08: Validate ingestion recovery and deliver the data runbook

Owner: @alisamanukyann | Area: Data / DB | Phase: Release | Priority: P0

Verify production ingestion behavior and make collection reproducible for teammates.

Dependencies: [A06](#a06), [A07](#a07), [C08](#c08)

Acceptance criteria:

- [ ] Demonstrate initial load, repeated load, price change, and recovery from a failed run.
- [ ] Verify failed collection does not clear active inventory and incomplete records stay traceable.
- [ ] Deliver source limitations, rerun instructions, and a reproducible demo dataset for the final demo.

<a id="b01"></a>

## B01: Model the municipal real estate ontology

Owner: @Lazr22 | Area: ML / Ontology | Phase: Foundation | Priority: P0

Define the ontology for properties, listings, districts, infrastructure, estimates, and risk evidence.

Dependencies: None.

Acceptance criteria:

- [ ] Commit an OWL/RDF ontology and a readable class/relationship diagram.
- [ ] Provide competency questions and examples covering Yerevan locations and property characteristics.
- [ ] Demonstrate consistency and sample queries/inferences with Protégé or RDFLib.

<a id="b02"></a>

## B02: Define the feature and evaluation contract

Owner: @Lazr22 | Area: ML / Ontology | Phase: Foundation | Priority: P0

Agree with data and backend owners on model inputs, outputs, and evaluation methodology.

Dependencies: [C01](#c01)

Acceptance criteria:

- [ ] Define feature types, missing-value behavior, units, and prediction response structure.
- [ ] Specify chronological splits and duplicate-group isolation to prevent leakage.
- [ ] Define baseline, error metrics, interval coverage/width, and neighborhood-level evaluation.

<a id="b03"></a>

## B03: Implement the comparable-property median baseline

Owner: @Lazr22 | Area: ML / Ontology | Phase: MVP | Priority: P0

Create an explainable valuation baseline using comparable rental listings.

Dependencies: [B02](#b02), [A03](#a03)

Acceptance criteria:

- [ ] Return expected monthly USD rent, comparable count, and selection explanation.
- [ ] Handle sparse comparables with a documented fallback or insufficient_data result.
- [ ] Provide a callable interface and deterministic checks on controlled examples for backend integration.

<a id="b04"></a>

## B04: Train and compare the rental price model

Owner: @Lazr22 | Area: ML / Ontology | Phase: Intelligence | Priority: P0

Train a CatBoost regressor and compare it fairly with the baseline.

Dependencies: [A06](#a06), [B03](#b03)

Acceptance criteria:

- [ ] Run a reproducible experiment on the agreed split and report baseline/model MAE and median absolute error.
- [ ] Report neighborhood results and investigate large errors and data leakage.
- [ ] Save preprocessing, feature schema, model artifact, and version metadata; keep the baseline fallback if ML is worse.

<a id="b05"></a>

## B05: Calibrate prediction intervals and valuation confidence

Owner: @Lazr22 | Area: ML / Ontology | Phase: Intelligence | Priority: P0

Add empirically evaluated rental price intervals and defensible abstention behavior.

Dependencies: [B04](#b04)

Acceptance criteria:

- [ ] Calibrate intervals without using test labels and report held-out coverage and width.
- [ ] Implement within_range, above_range, below_range, and insufficient_data consistently.
- [ ] Evaluate sparse, missing-feature, and out-of-distribution examples; explain confidence limitations.

<a id="b06"></a>

## B06: Implement ontology rules and valuation explanations

Owner: @Lazr22 | Area: ML / Ontology | Phase: Intelligence | Priority: P0

Connect geographic facts and property descriptions to traceable inference and readable explanations.

Dependencies: [B01](#b01), [A05](#a05), [B03](#b03)

Acceptance criteria:

- [ ] Implement versioned rules with evidence for proximity and description/location inconsistencies.
- [ ] Show at least three representative inference examples, including a missing-data case.
- [ ] Separate inferred facts from learned price effects and supply structured explanations to backend.

<a id="b07"></a>

## B07: Package the inference interface for backend integration

Owner: @Lazr22 | Area: ML / Ontology | Phase: Intelligence | Priority: P0

Deliver a versioned prediction package usable by the FastAPI application.

Dependencies: [B05](#b05), [B06](#b06)

Acceptance criteria:

- [ ] Provide one documented inference entry point matching the shared contract.
- [ ] Include model/rule versions, data freshness, interval, factors, and fallback behavior.
- [ ] Verify artifact loading and predictions in the backend container with a reproducible example.

<a id="b08"></a>

## B08: Deliver model and ontology evaluation evidence

Owner: @Lazr22 | Area: ML / Ontology | Phase: Release | Priority: P0

Prepare evidence for the final defense and document practical limitations.

Dependencies: [B07](#b07)

Acceptance criteria:

- [ ] Publish a model card, reproducible evaluation commands, and comparison charts.
- [ ] Show ontology competency-question results and rule validation examples.
- [ ] Evaluate risk-related examples separately from price errors; state limitations without claiming unmeasured fraud accuracy.

<a id="c01"></a>

## C01: Finalize shared data, API, and integration contracts

Owner: @Artyomkrtchyan | Area: Backend | Phase: Foundation | Priority: P0

Coordinate the contracts used by all four components before parallel implementation.

Dependencies: None.

Acceptance criteria:

- [ ] Publish OpenAPI schemas for listings, coordinate valuations with standard deviations, estimates, market indexes, and reviews, including validation, pagination, and errors.
- [ ] Agree units, USD conversion semantics, nullable fields, identifiers, and model inputs with the owners.
- [ ] Provide synthetic request/response fixtures so frontend and ML can work independently.

<a id="c02"></a>

## C02: Bootstrap FastAPI and the local Docker environment

Owner: @Artyomkrtchyan | Area: Backend | Phase: Foundation | Priority: P0

Create a runnable backend and shared local environment.

Dependencies: [C01](#c01)

Acceptance criteria:

- [ ] Docker Compose starts the API and PostgreSQL/PostGIS with documented setup.
- [ ] Provide health checks, environment examples, database configuration, and a model stub.
- [ ] Verify a clean setup and basic API behavior without external credentials.

<a id="c03"></a>

## C03: Implement listing search, details, and geographic APIs

Owner: @Artyomkrtchyan | Area: Backend | Phase: MVP | Priority: P0

Serve normalized listing data through the agreed API.

Dependencies: [C02](#c02), [A02](#a02)

Acceptance criteria:

- [ ] Implement district/price/rooms/area filters, stable pagination, details, and bounded map queries.
- [ ] Return source links, freshness, missing-data states, and inactive status consistently.
- [ ] Verify query validation, no-result cases, and representative database-backed responses.

<a id="c04"></a>

## C04: Integrate valuation and ontology results

Owner: @Artyomkrtchyan | Area: Backend | Phase: MVP | Priority: P0

Expose baseline valuation first and support the versioned ML package when available.

Dependencies: [C03](#c03), [B03](#b03)

Acceptance criteria:

- [ ] Expose expected USD rent, interval when available, factors, versions, and insufficient-data behavior.
- [ ] Persist estimates with freshness/version metadata and avoid silently returning stale results.
- [ ] Integrate the baseline for MVP, then B07 for final delivery; verify success and model-failure paths.

<a id="c05"></a>

## C05: Implement risk signals and the protected review workflow

Owner: @Artyomkrtchyan | Area: Backend | Phase: Intelligence | Priority: P0

Create explainable risk rules and a reviewer-only queue with recorded decisions.

Dependencies: [C04](#c04), [A04](#a04), [B06](#b06)

Acceptance criteria:

- [ ] Keep price anomalies separate from fraud-risk evidence; version rules and prevent duplicate signals.
- [ ] Implement queue filters, status changes, decision reasons, and audit timestamps.
- [ ] Protect reviewer endpoints with authentication/authorization and verify unauthorized requests are rejected.

<a id="c06"></a>

## C06: Expose market analytics and data freshness

Owner: @Artyomkrtchyan | Area: Backend | Phase: Intelligence | Priority: P1

Provide frontend-ready neighborhood and trend endpoints.

Dependencies: [C03](#c03), [A07](#a07)

Acceptance criteria:

- [ ] Return periods, USD units, sample counts, and source freshness with every aggregate.
- [ ] Handle sparse data and empty periods without fabricated values.
- [ ] Verify API responses against data-layer aggregates and the agreed chart fixtures.

<a id="c07"></a>

## C07: Add pull-request checks and container build workflows

Owner: @Artyomkrtchyan | Area: Infra | Phase: MVP | Priority: P0

Create CI for meaningful component checks and reproducible container builds.

Dependencies: [C02](#c02), [D02](#d02)

Acceptance criteria:

- [ ] Run backend/data/ML checks and frontend type/build checks as components become available.
- [ ] Build required Docker images and document version/tag conventions.
- [ ] Verify a failing check is reported and configure PR review/protection where supported by the repository plan.

<a id="c08"></a>

## C08: Provision and deploy the AWS application with Terraform

Owner: @Artyomkrtchyan | Area: Infra | Phase: Release | Priority: P0

Deploy the application using the agreed AWS architecture.

Dependencies: [C03](#c03), [C07](#c07), [D07](#d07)

Acceptance criteria:

- [ ] Terraform defines frontend S3/CloudFront, backend ECS/ECR, RDS/PostGIS, artifact storage, networking, and logging.
- [ ] Configure HTTPS, appropriate CORS, private database access, and secrets handling; record cost assumptions before provisioning.
- [ ] Deploy versioned images/frontend builds and document migrations, rollback, and teardown; do not place credentials in Git.

<a id="c09"></a>

## C09: Configure weekly cron ingestion and operational monitoring

Owner: @Artyomkrtchyan | Area: Infra | Phase: Release | Priority: P0

Run ingestion on schedule and make failures visible.

Dependencies: [C08](#c08), [A04](#a04)

Acceptance criteria:

- [ ] Configure an explicit weekly cron expression in Terraform for EventBridge Scheduler (initial schedule: Sunday 03:00, Asia/Yerevan) to launch the collection ECS task with overlap prevention; make the schedule configurable.
- [ ] Record run status, retries, and freshness; add failure visibility through CloudWatch.
- [ ] Demonstrate a manual run, a failed run, and recovery without clearing inventory; document rerun steps.

<a id="c10"></a>

## C10: Complete end-to-end release verification and the demo runbook

Owner: @Artyomkrtchyan | Area: Backend | Phase: Release | Priority: P0

Coordinate final integration and produce a reproducible release demonstration.

Dependencies: [A08](#a08), [B08](#b08), [D08](#d08), [C05](#c05), [C06](#c06), [C09](#c09), [C11](#c11), [D09](#d09), [E05](#e05)

Acceptance criteria:

- [ ] Verify collection → database → valuation → signals → API → UI → reviewer decision using real and controlled examples.
- [ ] Record resolved integration defects, deployed version, smoke checks, and known limitations.
- [ ] Deliver setup/deployment/demo instructions with a baseline-vs-ML example and rollback procedure.

<a id="d01"></a>

## D01: Design the user journeys and screen contracts

Owner: @manemazmand | Area: Frontend | Phase: Foundation | Priority: P0

Define the catalogue, detail, analytics, and reviewer journeys before implementation.

Dependencies: None.

Acceptance criteria:

- [ ] Provide lightweight wireframes and a shared UI structure for desktop and mobile.
- [ ] Define loading, empty, error, insufficient-data, and stale-data states.
- [ ] Review required API data with backend and align labels so risk signals are not presented as fraud verdicts.

<a id="d02"></a>

## D02: Bootstrap React/TypeScript and a mock API layer

Owner: @manemazmand | Area: Frontend | Phase: Foundation | Priority: P0

Create the frontend shell and a mock-backed integration boundary.

Dependencies: [D01](#d01), [C01](#c01)

Acceptance criteria:

- [ ] Vite app runs with routing, reusable layout, and environment-based API configuration.
- [ ] Use shared synthetic fixtures behind a typed API client.
- [ ] Provide type/build checks and demonstrate switching between mock and real API modes.

<a id="d03"></a>

## D03: Build the listing catalogue and filters

Owner: @manemazmand | Area: Frontend | Phase: MVP | Priority: P0

Implement browsing of Yerevan rentals with useful comparisons.

Dependencies: [D02](#d02)

Acceptance criteria:

- [ ] Display monthly USD rent, area, rooms, district, and source freshness.
- [ ] Implement filters and pagination with URL state and clear/reset behavior.
- [ ] Verify loading, empty, error, and missing-field cases; integrate C03 when available.

<a id="d04"></a>

## D04: Build listing details and the valuation explanation view

Owner: @manemazmand | Area: Frontend | Phase: MVP | Priority: P0

Show the requested rent alongside the estimated range and explanation.

Dependencies: [D03](#d03)

Acceptance criteria:

- [ ] Display expected price, interval when available, comparables, factors, versions/freshness, and original source link.
- [ ] Separate price status from risk signals and handle insufficient_data without invented scores.
- [ ] Use responsive layout and connect the real C04 endpoint when ready.

<a id="d05"></a>

## D05: Implement the interactive property and infrastructure map

Owner: @manemazmand | Area: Frontend | Phase: Intelligence | Priority: P1

Make a framed map introduction the opening Browse experience, with explicit full-screen mode, and connect map exploration to the listing catalogue.

Dependencies: [D03](#d03), [A05](#a05), [C03](#c03)

Acceptance criteria:

- [ ] Render geolocated listings, selected property details, and relevant infrastructure with MapLibre GL JS.
- [ ] Keep filters and map selection consistent and handle missing coordinates.
- [ ] Document map/tile attribution and verify marker behavior and bounded-query performance on representative data.
- [ ] Open Browse with a framed map below a short headline, explicit full-screen mode and easy access to filters; preserve page scrolling, an accessible list alternative and usable mobile layout.
- [ ] Provide 2D/3D switching with building extrusions where verified Yerevan footprint/height data is available; document coverage and provide a 2D fallback without invented heights.
- [ ] Define the colored rental layer with units, legend, sample counts and freshness; keep insufficient-data areas neutral. Real aggregate integration requires A07/C06, and any synthetic preview must be labeled.

The map renderer and design direction are agreed; tile/style provider, Yerevan 3D data coverage and provider costs remain D05 selection/validation work. Existing D03/A05/C03 dependencies remain; the real aggregate color layer also requires A07/C06. No API contract changes or implementation are implied by this plan update.

<a id="d06"></a>

## D06: Build neighborhood market analytics

Owner: @manemazmand | Area: Frontend | Phase: Intelligence | Priority: P1

Visualize neighborhood asking-price indexes and trends with Recharts.

Dependencies: [D02](#d02), [C06](#c06)

Acceptance criteria:

- [ ] Provide neighborhood/time controls and clearly labeled USD/month and USD/m² measures.
- [ ] Show observation counts, periods, and freshness; distinguish missing data from zero.
- [ ] Verify rendered values against API fixtures and real aggregate responses.

<a id="d07"></a>

## D07: Build the authenticated reviewer interface

Owner: @manemazmand | Area: Frontend | Phase: Intelligence | Priority: P0

Enable authorized reviewers to inspect signals and record decisions.

Dependencies: [D02](#d02), [C05](#c05)

Acceptance criteria:

- [ ] Provide login/session handling, queue filters, evidence details, and review actions.
- [ ] Require a decision reason and show saved status/history without duplicate submissions.
- [ ] Handle expired/unauthorized sessions and connect the protected backend workflow.

<a id="d08"></a>

## D08: Validate the integrated UI and prepare the frontend demo

Owner: @manemazmand | Area: Frontend | Phase: Release | Priority: P0

Verify the complete frontend against the deployed application.

Dependencies: [D04](#d04), [D05](#d05), [D06](#d06), [D07](#d07), [C08](#c08)

Acceptance criteria:

- [ ] Add meaningful Playwright coverage for browsing, filters, valuation, analytics, and reviewer decisions.
- [ ] Check mobile layout, keyboard navigation, empty/error/stale states, and production API configuration.
- [ ] Resolve UI integration defects and deliver a short demo sequence with screenshots and known limitations.

<a id="b09"></a>

## B09: Build the coordinate-based price statistics and assessment pipeline

Owner: @Lazr22 | Area: ML / Ontology | Phase: MVP | Priority: P0

Implement the required Python analysis pipeline using Pandas and Scikit-Learn to assess rental prices around supplied coordinates.

Dependencies: [B02](#b02), [B03](#b03), [A05](#a05)

Acceptance criteria:

- [ ] Define radius/time/property comparability rules, duplicate handling, and minimum sample size with the data owner.
- [ ] Return count, mean, sample standard deviation (n−1) in USD/month and USD/m² where available, cohort metadata, and a valuation assessment; distinguish observed dispersion from prediction intervals.
- [ ] Support coordinate-only neighborhood reference and property-specific valuation when enough inputs exist; verify sparse, out-of-coverage, and known synthetic samples without fabricating values.

<a id="c11"></a>

## C11: Expose the coordinate valuation and price standard deviation REST endpoint

Owner: @Artyomkrtchyan | Area: Backend | Phase: MVP | Priority: P0

Implement POST /api/v1/valuations for supplied coordinates, optional property features, local dispersion, and valuation assessments.

Dependencies: [C03](#c03), [C04](#c04), [B09](#b09)

Acceptance criteria:

- [ ] Validate coordinate bounds, Yerevan coverage, supported radius, and property inputs; document request/response examples in OpenAPI.
- [ ] Integrate B09 and return cohort size, units, mean, standard deviations, valuation assessment, freshness, and model/rule versions; clearly label coordinate-only results as area references.
- [ ] Verify controlled-sample numeric results, insufficient-data/null behavior, invalid inputs, and an end-to-end coordinate request through the deployed API.

<a id="d09"></a>

## D09: Add coordinate-based valuation lookup and price dispersion results

Owner: @manemazmand | Area: Frontend | Phase: MVP | Priority: P0

Let users request an assessment for a coordinate pair or map selection and inspect local price dispersion.

Dependencies: [D02](#d02), [C11](#c11)

Acceptance criteria:

- [ ] Provide validated coordinate input or map selection and optional property characteristics connected to POST /api/v1/valuations.
- [ ] Display the assessment, comparable count, search radius/time window, freshness, and standard deviations with explicit USD/month and USD/m² units.
- [ ] Explain that standard deviation is observed market dispersion, keep it separate from prediction intervals, and handle insufficient data, unsupported locations, and request errors.

<a id="e01"></a>

## E01: Inventory information assets and assess application security risks

Owner: @manemazmand | Area: Docs / QA | Phase: Foundation | Priority: P0

Identify FairRent information assets, trust boundaries and security risks, and agree proportionate controls with component owners.

Dependencies: None.

Acceptance criteria:

- [ ] Document asset ownership and classification for listing data, reviewer identities, credentials, model artifacts and logs; assess confidentiality, integrity and availability needs.
- [ ] Create a data-flow diagram and STRIDE threat model; record likelihood, impact, controls, residual risk and remediation owners in a prioritized risk register.
- [ ] Map selected controls to NIST CSF or CIS Controls and document access, secret-handling and incident-reporting procedures; do not claim framework certification.

<a id="e02"></a>

## E02: Add security checks and remediate dependency and container findings

Owner: @manemazmand | Area: Infra | Phase: MVP | Priority: P0

Integrate actionable secret, dependency and container security checks into the existing delivery workflow with the CI owner.

Dependencies: [C02](#c02)

Acceptance criteria:

- [ ] Add secret and dependency checks and container-image scanning where supported; verify detection using harmless synthetic fixtures and document severity handling and time-limited exceptions.
- [ ] Review workflow token permissions, untrusted PR inputs, action references and artifact access with Artyom; document fixes without introducing cloud credentials into CI.
- [ ] Review container runtime privileges, unnecessary packages and exposed ports; fix verified findings and record retest evidence.

<a id="e03"></a>

## E03: Verify application authorization and untrusted input handling

Owner: @manemazmand | Area: Backend | Phase: Intelligence | Priority: P0

Verify reviewer access controls, frontend sessions and safe handling of untrusted listing and request data.

Dependencies: [C05](#c05), [D07](#d07)

Acceptance criteria:

- [ ] Add tests for missing, expired and invalid tokens, incorrect reviewer role, object access, forbidden review updates and concurrency conflicts; distinguish application roles from AWS IAM.
- [ ] Verify listing text rendering, external links, session/token handling, query parameterization and safe errors; test representative XSS and injection inputs against owned test environments.
- [ ] Verify pagination, bounded geographic queries, request-size/time limits and URL-fetching restrictions where applicable; coordinate implementation fixes and retest with component owners.

<a id="e04"></a>

## E04: Verify transport security and data and model artifact integrity

Owner: @manemazmand | Area: Docs / QA | Phase: Release | Priority: P0

Verify protected transport, data handling and model artifact integrity in the deployed application with infrastructure and data owners.

Dependencies: [C08](#c08), [A06](#a06), [B07](#b07)

Acceptance criteria:

- [ ] Inspect the deployed HTTPS certificate chain, hostname and validity using OpenSSL or equivalent tools; verify HTTP-to-HTTPS behavior and absence of mixed content, reporting AWS configuration changes to Artyom.
- [ ] Verify dataset and model artifact checksums against a trusted manifest and demonstrate rejection of a modified artifact; distinguish integrity hashes from authentication or digital signatures.
- [ ] Review application database privileges, sensitive log fields, data exports and reachable service boundaries; verify agreed protections without changing AWS resources, IAM or cloud permissions.

<a id="e05"></a>

## E05: Complete security verification and the incident response runbook

Owner: @manemazmand | Area: Docs / QA | Phase: Release | Priority: P0

Verify security fixes before release and make application incident handling reproducible for the team.

Dependencies: [E01](#e01), [E02](#e02), [E03](#e03), [E04](#e04)

Acceptance criteria:

- [ ] Perform scoped manual and automated security checks against owned staging services; record reproduction, impact, fix and retest results, with explicit owner acceptance for unresolved release risks.
- [ ] Document detection, triage, containment, recovery, evidence handling and post-incident review; rehearse a simulated unauthorized reviewer action or synthetic credential-exposure scenario.
- [ ] Verify audit events identify actor, action, outcome and UTC time without tokens or sensitive payloads; summarize findings and residual risks for the release demo.

<a id="s01"></a>

## S01: Configure the Linux environment and secure access

Owner: @manemazmand | Area: Infra | Phase: Release | Priority: P2

Optional after the core release and security work, only if time remains. Configure a Linux environment for the Compose application and document access, networking and storage.

Dependencies: [C10](#c10), [E05](#e05), [D08](#d08)

Acceptance criteria:

- [ ] Document VM OS/resources, a non-root administrator, SSH key access, file permissions and firewall rules; verify access before restricting SSH.
- [ ] Start the API and PostGIS from the repository instructions, verify health/readiness, and document container networking and persistent storage.
- [ ] Keep secrets and real listing data out of Git; provide a reproducible setup and teardown guide with sanitized command output.

<a id="s02"></a>

## S02: Document service monitoring and Linux troubleshooting

Owner: @manemazmand | Area: Infra | Phase: Release | Priority: P2

Optional after the core release and security work, only if time remains. Implement service monitoring and document application and host diagnostics.

Dependencies: [S01](#s01)

Acceptance criteria:

- [ ] Document checks for API health/readiness, Compose status/logs, listening ports, disk space, memory and host services.
- [ ] Provide a small shell check script with meaningful exit codes and no credentials in output; demonstrate healthy and unavailable database states.
- [ ] Document log locations, bounded log retention and a symptom-to-diagnosis checklist with sanitized evidence.

<a id="s03"></a>

## S03: Implement and verify database backup and restore

Owner: @manemazmand | Area: Infra | Phase: Release | Priority: P2

Optional after the core release and security work, only if time remains. Implement reproducible PostgreSQL/PostGIS backup and restore procedures and verify recovery using synthetic data.

Dependencies: [S01](#s01)

Acceptance criteria:

- [ ] Provide documented pg_dump/pg_restore commands or shell scripts, backup naming, restricted permissions and a retention policy; exclude backups from Git.
- [ ] Restore into a separate disposable database or Compose project and verify synthetic rows and PostGIS functionality without overwriting the working database.
- [ ] Record backup/restore duration, database and PostGIS versions, failure handling and rerun steps; document how the procedure relates to production RDS backups.

<a id="s04"></a>

## S04: Validate service recovery and deliver the operations runbook

Owner: @manemazmand | Area: Infra | Phase: Release | Priority: P2

Optional after the core release and security work, only if time remains. Verify application recovery from service failures and deliver reproducible operating procedures.

Dependencies: [S02](#s02), [S03](#s03)

Acceptance criteria:

- [ ] Reproduce database unavailability, an occupied API port and invalid configuration in a controlled environment; record symptoms, diagnosis and recovery.
- [ ] Demonstrate recovery after VM reboot and a database restore drill; verify health/readiness and retained synthetic data.
- [ ] Publish a runbook covering access, startup/shutdown, logs, backup/restore, recovery and environment teardown; have another teammate reproduce one procedure.
