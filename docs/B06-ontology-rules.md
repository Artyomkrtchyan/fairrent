# B06 - Ontology rules and valuation explanations

Rules version: `b06-rules-v1.0.0` (`ml/ontology_rules.py`). Ontology: `ontology/real_estate_ontology.ttl` v1.1.0.

## What is separated, and why

| Kind | Source | Contract object | Meaning |
|---|---|---|---|
| Inferred fact | rules over coordinates + A05 registry (`yerevan-geo-v1`) | `Factor` (origin `ontology`) | e.g. 257 m from a metro station. Says nothing about price. |
| Consistency finding | rules over listing fields/text | `RiskSignal` (`risk_evidence`) | Fields contradict each other or the map pin. Review evidence, not fraud. |
| Price anomaly | asking price vs the B05 calibrated interval | `RiskSignal` (`price_anomaly`) | Outside the interval. Not fraud; asking prices are not signed rents. |
| Learned price effect | CatBoost SHAP (`ml/attributions.py`) | `Attribution` / `Factor` (origin `model`) | What the model learned for this estimate. |

The ontology declares `InferredFact`, `RiskEvidence` and `LearnedPriceEffect` as `owl:AllDisjointClasses`, and
`ontology_graph.separation_holds` checks it. The demo's price-only `HIGH`/predatory labels are removed
(`hasSeverity` is deprecated); a price anomaly is now a `PriceAnomalyFinding` with category `price_anomaly`.

## Rules

Every rule has an id, version, parameters and limitations (`ontology_rules.registry()`).

- `GEO-PROX-METRO|UNIVERSITY|CENTER` - proximity facts (500 m / 1000 m thresholds, provisional). Straight-line distance.
- `GEO-DISTRICT-SUPPORT` - flags when none of the reference listings around the pin (~1 km cells, 3x3 block, fitted on the train split by `python -m ml.fit_district_support`) carry the stated district. Needs >= 20 reference listings, otherwise `unknown`.
- `DESC-AREA|ROOMS|FLOOR|DISTRICT-MATCH` - text vs field. Only meaningful when text and fields come from different sources; the list.am scrape parses fields from the title, so these are `unknown`/`clear` there.
- `FEAT-AREA-PLAUSIBILITY` - area 10-600 m2 and 8-150 m2 per room.
- `PRICE-OUTSIDE-INTERVAL` - needs a B05 interval; otherwise `unknown`.

Missing data gives `unknown` with a `reason`, never a silent "false" and never a flag.

## Backend hand-off

`ontology_rules.explain_valuation(model_input, district_support=..., learned_attributions=...)` returns
`inferred_facts`, `consistency_checks`, `learned_price_effects`, `factors` (contract `Factor`) and `text`.
`evaluate_listing` + `listing_signals` produce contract `RiskSignal`s with deterministic uuid5 ids
(listing, rule, rules version, evidence), so replays do not create duplicate queue entries.
`attributions_from_shap` / `explain_with_catboost` produce `Attribution`s (impact = share of absolute SHAP mass).

## Examples

`python -m ontology.demo_inference` runs three cases: typical, inconsistent (district vs pin, implausible area,
price above interval) and missing data (no coordinates/area/interval). Expected output is pinned in
`ontology/examples/b06_inference_examples.json` (regenerate with `--write` after a deliberate rule change).

## Measured on the real-scrape simulation (4,781 validation+test rows)

District support: 1 flagged, 212 unknown (sparse area). Area plausibility: 2 flagged. Description rules: all
`unknown` (the export has no free text). Proximity: 755 metro / 946 university / 1,563 centre facts hold.

## Limitations

Thresholds are provisional. Pins are approximate. Text rules are untested against independent descriptions.
Flag rates are review workload, not accuracy: no labelled fraud data exists, so precision is unmeasured.
