# C04 integration progress — 2026-10-21

Branch: feat/C04-valuation-integration. Base: main ce5055b plus C03 d857b6a.
C03 remains a separate unmerged PR; this integration branch depends on it.

## B03 review

The three original deterministic tests pass. B03 supplies a callable median
price-per-area baseline, count, selection explanation and sparse-data abstention.
It is usable as a calculation primitive, but is not ready as an unguarded API model.

Reproduced on synthetic data:
- Three observations dated 2020-01-01 produce a successful USD 840 estimate and
  freshness=10 on 2026-10-21. max_freshness_days is unused.
- A coordinate-only request at (0, 0) returns USD 720 from Yerevan observations.
  Coordinates are checked only for presence, never used for distance selection.
- Zero reference area produces an infinite estimated price.
- Coordinate-only explanation calls the configured 60 sqm constant a district
  median, although no median is fitted.

No trained-model metrics or real-data accuracy claims were evaluated.

## Implemented first C04 slice

backend/valuation_gateway.py wraps the unchanged B03 implementation. It accepts
an explicit versioned reference snapshot, applies radius and observation-window
bounds, excludes future/invalid observations and the subject duplicate group,
keeps one observation per group, applies district and optional room selection,
and recomputes unit prices. Actual freshness replaces B03's hardcoded number.
Model exceptions become ModelUnavailable rather than insufficient_data.
Intervals and attributions remain absent because B03 does not supply them.

This is an internal integration seam, not the C01 public response schema.
The configured 60 sqm coordinate reference is explicitly labeled; it is not
represented as a fitted district median. The snapshot owner must supply an
appropriate frozen reference/training snapshot with a reproducible version.

Validation: 12 passed (3 original B03 tests + 9 C04 adapter cases).
Runtime used pandas 2.3.3 and numpy 2.2.2. No new runtime dependency is added to
the deployed API while this module is not imported by an HTTP route.

## Remaining C04 work

- Agree reference snapshot provenance and versioning with the ML owner; district
  reference areas and municipal boundaries are not supplied by B03.
- Add the C01 valuation endpoint and complete typed response mapping, including
  cohort, freshness, version, area-reference, and explicit failure semantics.
- Persist estimates with input/dataset/model/policy versions and source timestamps;
  define expiry and invalidation rather than silently reuse stale results.
- Connect listing details, verify PostgreSQL round trips and contract validation.
- Package pandas/numpy for API deployment and add CI coverage.
- Provide a replaceable B07 provider when the versioned package is delivered.

C04 is started, not complete. No public API or database migration was changed.
