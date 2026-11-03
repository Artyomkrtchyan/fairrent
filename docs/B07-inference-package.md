# B07 - Inference package for backend integration

Interface version `b07-v1`. Implements the in-process interface proposed in `docs/contract-semantics.md`
("ML and statistics"). Code: `ml/inference.py`, `ml/package_inference.py`, `ml/verify_package.py`.

## 1. Build the package (once per model/calibration)

```
python -m ml.package_inference --b04 artifacts/b04/<v> --b05 artifacts/b05/<v> --snapshot data/processed/<dataset> --version <package-version>
```

Writes `artifacts/b07/<version>/` (git-ignored; share it like the B04/B05 artifacts): `model.cbm`,
`preprocessing.json`, `interval_calibration.json` (with the serving gate), `district_support.json` (B06 reference,
train split only), `package.json` (versions, data_as_of, thresholds, training null rates, limitations) and
`SHA256SUMS.json`. It refuses to build if the B04/B05 checksums, the model hash or the snapshot hash disagree, if
B04's decision is not `ml`, or if the version already exists (packages are immutable).

## 2. Call it

```python
from ml import inference
package = inference.load_package("artifacts/b07/<version>")        # or set FAIRRENT_MODEL_PACKAGE and omit `package`
result = inference.assess(model_input, comparables=cohort, package=package)
```

`model_input` is the contract's `ModelInput` (strictly validated; unknown fields such as the asking price are
rejected). `comparables` is the B09 cohort the backend already computed: `[{"price_usd": 600, "area_sqm": 50}, ...]`
(area may be null). `assess` returns the B02 blocks `coordinates`, `versions`, `valuation_assessment`,
`observed_market_statistics`, `ml_prediction_interval`, `feature_attributions`, `area_reference`, plus
`explanation` (text), `ontology` (B06: inferred facts, consistency checks, learned effects, factors) and
`provenance` (package/model/calibration/rules/geography/dataset versions, `model_data_as_of`, evidence level,
`interval_withheld_reasons`, `fallback`, `abstention_reason`).

The backend adds `request_id`, `cohort`, `freshness`, `price_status` and `kind`, where
`kind = inference.kind_for(result)` (`property_valuation` only when the model produced an estimate).
`price_status = intervals.price_status(asking_price_usd_month, result["ml_prediction_interval"])`.
Distances missing from the input are computed from the A05 registry; the district may be an id, alias or label.

## 3. What comes back, by case

| Case | `assessment_status` | estimate | interval | notes |
|---|---|---|---|---|
| area and rooms known, evidence sufficient, gate passes | `VALUATION_SUCCESS` | model prediction | calibrated | SHAP attributions + rule explanation |
| area or rooms unknown | `COORDINATE_BASELINE_ONLY` | observed cohort mean (not a prediction) | null | `area_reference` discloses the training-fitted reference area |
| < 3 comparables, or `as_of` older than 60 days or missing | `INSUFFICIENT_DATA_ABSTAIN` | null | null | observed statistics stay visible |
| serving gate: area outside training range, sparse local training data, prediction < $1 | `INSUFFICIENT_DATA_ABSTAIN` | null | null | reason in `provenance.interval_withheld_reasons` |
| package missing/corrupt, or model raises | `INSUFFICIENT_DATA_ABSTAIN` | null | null | `versions.model_version = "unavailable"` (load failure), `provenance.fallback` set; no crash |

Exceptions (not abstentions): `InputValidationError` -> 422; `OutsideCoverageError` -> 400 `outside_coverage`;
`PackageError` is raised only by `load_package` (so a deploy can fail fast), never by `assess`.

## 4. Verify in a container

Python 3.10 (the backend image) with only the inference dependencies (`ml/requirements-inference.txt`: numpy, pandas,
catboost; no scikit-learn, rdflib or database libraries):

```
docker build -f ml/docker/Dockerfile.verify -t fairrent-b07-verify .
docker run --rm -v "<absolute path>\artifacts\b07\<version>:/package:ro" fairrent-b07-verify
```

It prints the versions, runs the cases in `ml/examples/b07_requests.json`, validates each assembled
`ValuationResponse` against `contracts/openapi.json` and ends with `VERIFIED` (exit code 0). The same command
without Docker: `python -m ml.verify_package --package artifacts/b07/<version>`.

To run inside the backend's own image, its build context must include `ml/` and `data_pipeline/geography.py`
(today it is `./backend`): change `compose.yml` to `context: .` + `dockerfile: backend/Dockerfile`, copy those paths and
`pip install -r ml/requirements-inference.txt`. That edit belongs to the backend owner; nothing in `backend/` was
changed here, and `backend/model_stub.py` is untouched until they wire `assess` in.

## 5. Decisions and limits (need owner confirmation)

- Gate failures abstain rather than returning a point estimate without an interval (no silent extrapolation).
- Coverage is a coarse provisional bounding box (`provisional-bbox-v1`); the authoritative A05 boundary does not exist
  yet. The backend can enforce a PostGIS boundary first.
- Thresholds (3 comparables, 60 days) are the provisional contract values.
- Training district names are the registry display names; distances computed at inference use the same A05 function.
  `package.json.training_null_rate` shows which features had data in training: a feature that was 100% null in
  training (for example distances in a scrape without enrichment) is ignored by the model.
- The package inherits B04/B05 evidence limits (`provenance.evidence_level`, `temporal_split`): a non-temporal split
  is an optimistic in-time estimate, and the 95% interval width target (0.22) was not met.
