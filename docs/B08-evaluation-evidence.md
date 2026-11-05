# B08 - Model and ontology evaluation evidence

One command regenerates all evidence from the B04 model, B05 calibration, B07 package and the dataset snapshot:

```
python -m ml.evaluation_evidence --b04 artifacts/b04/<v> --b05 artifacts/b05/<v> --package artifacts/b07/<v> \
    --snapshot data/processed/<dataset> --output docs/evidence/b08
```

It refuses to run unless the four inputs belong together (checksums, model hash, snapshot hash). The committed outputs
live in `docs/evidence/b08/`:

| File | Content |
|---|---|
| `model_card.md` | Intended use, versions, data, price error, intervals, ontology competency questions, risk rules, limitations, reproduction |
| `price_model_comparison.png`, `price_error_by_district.png`, `predicted_vs_actual.png` | CatBoost vs B03 baseline vs naive district median |
| `interval_calibration.png` | Observed vs nominal coverage and interval width against the provisional target |
| `rule_validation.png`, `price_anomaly_sensitivity.png` | Risk-rule behaviour (see below) |
| `evaluation_summary.json`, `risk_rule_validation.json`, `ontology_evaluation.json` | All numbers behind the card |
| `manifest.json` | Versions, input hashes, the exact command |

The output is deterministic (fixed seed): re-running on the same inputs and the same `--output` path reproduces the files byte for byte (the path appears in `manifest.json` and the card).

## How the evidence is separated

- **Price error** (card section 4): B04/B05 numbers taken from their reports (not recomputed) on the held-out test split.
- **Ontology** (section 5): the four competency questions (SPARQL) over a graph built from rule output for 300 held-out
  listings, the disjointness check of inferred facts versus learned price effects, the three worked examples
  (typical, inconsistent, missing data) and the proximity analysis (`ml/validate_proximity.py`): near-metro listings'
  price per m2 versus far ones, overall and inside districts. It shows the gap largely reflects location mix.
- **Risk rules** (section 6): evaluated on their own terms.
  - Rule outcomes on unmodified held-out listings (flagged / clear / unknown).
  - Detection of **injected** defects (district label swapped, area typo, text that disagrees with the fields),
    false flags on consistent synthetic text, behaviour with coordinates removed.
  - The price-anomaly flag rate on ordinary listings and how it grows as the asking price is multiplied.

## What this evidence does not claim

There are no fraud labels. The card therefore reports no fraud precision, recall or false-positive rate. Injected-defect
detection is near 100% by construction for the rules that test exactly that defect (it shows they fire; it does not show
real errors look like that), and is low for moderate errors the fixed bounds cannot see (reported). The price-anomaly rate
is about 1 - coverage by design, not a fraud rate. Description rules cannot be evaluated on real text because the export has
none.

## Publishing

```
git add docs/evidence/b08
git commit -m "B08: evaluation evidence for <dataset>"
```

Charts follow the dataviz reference palette (entity colours fixed across charts) and every bar is value-labelled.
