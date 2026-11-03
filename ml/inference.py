"""B07: the single inference entry point for the backend.

    from ml import inference
    package = inference.load_package("artifacts/b07/<version>")      # verifies checksums, loads artifacts
    result = inference.assess(model_input, comparables=cohort, package=package)

``assess`` implements the in-process interface proposed in docs/contract-semantics.md ("ML and statistics"):
it takes the contract's ``ModelInput`` and returns the B02 blocks ``coordinates``, ``versions``,
``valuation_assessment``, ``observed_market_statistics``, ``ml_prediction_interval``,
``feature_attributions`` and ``area_reference``, plus three documented extensions: ``explanation`` (text),
``ontology`` (B06 structured explanation, separating rule facts from learned price effects) and
``provenance`` (package, model, calibration, rule and data versions, and why anything was withheld).
The backend adds request_id, kind, cohort, freshness and price_status (see docs/B07-inference-package.md).

Division of labour (contract): the backend resolves the cohort (B09) and passes its monthly prices as
``comparables``; this package never sees the asking price. Every failure path is explicit:

* invalid input                      -> ``InputValidationError`` (HTTP 422)
* coordinates outside Yerevan        -> ``OutsideCoverageError`` (HTTP 400 ``outside_coverage``)
* artifacts missing/corrupt/unloadable, or the model raises
                                     -> a valid *abstention* response (``provenance.fallback``), never a crash
* too few comparables / stale data   -> ``INSUFFICIENT_DATA_ABSTAIN``
* area or rooms unknown              -> ``COORDINATE_BASELINE_ONLY`` (observed baseline, no interval)
* serving gate or low prediction     -> abstention with the reason code (no unsupported extrapolation)

Compatible with the backend image's Python 3.10.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

import pandas as pd

from ml import attributions as attr
from ml import intervals as iv
from ml import ontology_rules as rules
from ml import train_compare as tc

LOGGER = logging.getLogger(__name__)

INFERENCE_INTERFACE_VERSION = "b07-v1"
PACKAGE_SCHEMA_VERSION = "b07-package-v1"
PACKAGE_ENV_VAR = "FAIRRENT_MODEL_PACKAGE"

# Provisional thresholds from ml/CONTRACT.md and docs/contract-semantics.md (owner confirmation pending).
MIN_COMPARABLES = 3
MAX_SOURCE_AGE_DAYS = 60
# Coarse, provisional coverage box around Yerevan. The authoritative A05 boundary does not exist yet;
# the backend may enforce a PostGIS boundary before calling ``assess`` (docs/B07-inference-package.md).
COVERAGE_VERSION = "provisional-bbox-v1"
COVERAGE_BBOX = {"south": 40.05, "north": 40.30, "west": 44.35, "east": 44.66}

MODEL_INPUT_FIELDS = ("latitude", "longitude", "as_of", "radius_m", "window_days", "rooms", "floor",
                      "total_floors", "area_sqm", "renovation", "building_type", "district",
                      "distance_metro_m", "distance_center_m", "distance_university_m")
RENOVATIONS = ("cosmetic", "designer", "none")
BUILDING_TYPES = ("monolith", "stone", "panel")
STATUS_SUCCESS, STATUS_BASELINE, STATUS_ABSTAIN = (
    "VALUATION_SUCCESS", "COORDINATE_BASELINE_ONLY", "INSUFFICIENT_DATA_ABSTAIN")

_REQUIRED_FILES = ("model.cbm", "preprocessing.json", "interval_calibration.json", "district_support.json",
                   "package.json")


class InferenceError(Exception):
    """Base class."""


class InputValidationError(InferenceError):
    """The request violates the ModelInput contract (HTTP 422)."""


class OutsideCoverageError(InferenceError):
    """Valid coordinates outside the covered area (HTTP 400, code ``outside_coverage``)."""


class PackageError(InferenceError):
    """Package directory missing, altered, incomplete or not loadable."""


# ------------------------------------------------------------------------------ input


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def parse_utc(value: Any, field: str = "as_of") -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise InputValidationError(f"{field} must be an ISO 8601 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")      # 3.10's fromisoformat rejects a bare 'Z'
    except ValueError as error:
        raise InputValidationError(f"{field} is not a valid timestamp") from error
    return parsed.astimezone(timezone.utc)


def validate_model_input(raw: Mapping[str, Any]) -> Dict[str, Any]:
    """Strict ``ModelInput`` validation (contracts/openapi.json). Returns a normalised copy."""
    if not isinstance(raw, Mapping):
        raise InputValidationError("model input must be an object")
    unknown = sorted(set(raw) - set(MODEL_INPUT_FIELDS))
    if unknown:
        raise InputValidationError(f"unknown fields: {', '.join(unknown)} (asking price is never a model input)")
    missing = [f for f in ("latitude", "longitude", "as_of", "radius_m", "window_days") if raw.get(f) is None]
    if missing:
        raise InputValidationError(f"missing required fields: {', '.join(missing)}")
    out: Dict[str, Any] = {}

    def number(name: str, low: Optional[float] = None, high: Optional[float] = None, *, exclusive: bool = False,
               integer: bool = False, nullable: bool = True) -> None:
        value = raw.get(name)
        if value is None:
            if not nullable:
                raise InputValidationError(f"{name} is required")
            out[name] = None
            return
        if not _is_number(value) or (integer and (isinstance(value, float) and not value.is_integer())):
            raise InputValidationError(f"{name} must be {'an integer' if integer else 'a number'}")
        if low is not None and (value <= low if exclusive else value < low):
            raise InputValidationError(f"{name} is below the allowed minimum")
        if high is not None and value > high:
            raise InputValidationError(f"{name} is above the allowed maximum")
        out[name] = int(value) if integer else float(value)

    number("latitude", -90, 90, nullable=False)
    number("longitude", -180, 180, nullable=False)
    number("radius_m", 100, 5000, integer=True, nullable=False)
    number("window_days", 7, 90, integer=True, nullable=False)
    number("rooms", 1, integer=True)
    number("floor", 0, integer=True)
    number("total_floors", 1, integer=True)
    number("area_sqm", 0, exclusive=True)
    for name in ("distance_metro_m", "distance_center_m", "distance_university_m"):
        number(name, 0)
    if out["floor"] is not None and out["total_floors"] is not None and out["floor"] > out["total_floors"]:
        raise InputValidationError("floor cannot exceed total_floors")
    for name, allowed in (("renovation", RENOVATIONS), ("building_type", BUILDING_TYPES)):
        value = raw.get(name)
        if value is not None and value not in allowed:
            raise InputValidationError(f"{name} must be one of {', '.join(allowed)} or null")
        out[name] = value
    district = raw.get("district")
    if district is not None and (not isinstance(district, str) or not district.strip()):
        raise InputValidationError("district must be a non-empty string or null")
    out["district"] = district.strip() if isinstance(district, str) else None
    out["as_of"] = parse_utc(raw["as_of"]).strftime("%Y-%m-%dT%H:%M:%SZ")
    return out


def check_coverage(latitude: float, longitude: float) -> None:
    box = COVERAGE_BBOX
    if not (box["south"] <= latitude <= box["north"] and box["west"] <= longitude <= box["east"]):
        raise OutsideCoverageError(
            f"({latitude}, {longitude}) is outside the covered area ({COVERAGE_VERSION})")


def _district_label(value: Optional[str]) -> Optional[str]:
    """Training used the registry's display names (Kentron, Nork-Marash, ...); accept ids or aliases."""
    geo = rules._geography()
    if value is None or geo is None:
        return value
    district_id = rules._district_id(value)
    return geo.DISTRICTS[district_id][0] if district_id else None


def _with_distances(inp: Dict[str, Any]) -> Dict[str, Any]:
    """Backend-supplied distances win; missing ones are computed from the A05 registry (same function A05 uses)."""
    geo = rules._geography()
    if geo is None:
        return inp
    computed = geo.proximity_features(inp["latitude"], inp["longitude"])
    filled = dict(inp)
    for name in ("distance_metro_m", "distance_center_m", "distance_university_m"):
        if filled.get(name) is None:
            filled[name] = computed.get(name)
    return filled


# ------------------------------------------------------------------ observed statistics


def _sample_stats(values: Sequence[float]) -> Dict[str, Any]:
    n = len(values)
    return {"n": n, "mean": round(statistics.fmean(values), 2) if n else None,
            "std": round(statistics.stdev(values), 2) if n >= 2 else None}


def observed_statistics(comparables: Optional[Sequence[Mapping[str, Any]]], *, as_of: Optional[datetime],
                        now: datetime) -> Dict[str, Any]:
    """The contract's ``observed_market_statistics`` (n-1 sample standard deviation; independent monthly and
    per-m2 samples; never an interval). ``insufficient_data`` follows the provisional abstention rule."""
    prices: List[float] = []
    per_sqm: List[float] = []
    for item in comparables or []:
        price, area = item.get("price_usd"), item.get("area_sqm")
        if not _is_number(price) or price <= 0:
            continue
        prices.append(float(price))
        if _is_number(area) and area > 0:
            per_sqm.append(float(price) / float(area))
    monthly, area_stats = _sample_stats(prices), _sample_stats(per_sqm)
    age = None if as_of is None else max(0, (now - as_of).days)
    insufficient = monthly["n"] < MIN_COMPARABLES or age is None or age > MAX_SOURCE_AGE_DAYS
    return {"cluster_mean_price_usd": monthly["mean"], "observed_price_std_dev_usd": monthly["std"],
            "comparables_count": monthly["n"], "data_freshness_days": age, "insufficient_data": bool(insufficient),
            "cluster_mean_price_per_sqm_usd": area_stats["mean"],
            "observed_price_std_dev_per_sqm_usd": area_stats["std"], "area_comparables_count": area_stats["n"]}


# --------------------------------------------------------------------------- package


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class InferencePackage:
    """A verified, loaded B07 package (model + frozen preprocessing + calibration + gate + rule reference)."""

    def __init__(self, *, directory: Path, manifest: dict, model: Any, preprocessor: tc.Preprocessor,
                 calibration: iv.IntervalCalibration, gate: iv.ServingGate, district_support: rules.DistrictSupport):
        self.directory, self.manifest, self.model = directory, manifest, model
        self.preprocessor, self.calibration, self.gate = preprocessor, calibration, gate
        self.district_support = district_support

    @classmethod
    def load(cls, directory: Any) -> "InferencePackage":
        path = Path(directory)
        sums_path = path / "SHA256SUMS.json"
        if not path.is_dir() or not sums_path.is_file():
            raise PackageError(f"{path} is not a B07 package directory (SHA256SUMS.json not found)")
        try:
            sums = json.loads(sums_path.read_text(encoding="utf-8"))
            for name in _REQUIRED_FILES:
                if name not in sums or not (path / name).is_file():
                    raise PackageError(f"package file {name} is missing")
            for name, digest in sums.items():
                if not (path / name).is_file() or _sha256(path / name) != digest:
                    raise PackageError(f"package file {name} is missing or does not match SHA256SUMS.json")
            manifest = json.loads((path / "package.json").read_text(encoding="utf-8"))
            if manifest.get("package_schema_version") != PACKAGE_SCHEMA_VERSION:
                raise PackageError("unsupported package_schema_version")
            if manifest.get("rules_version") != rules.RULES_VERSION:
                raise PackageError(f"package was built for rules {manifest.get('rules_version')}, "
                                   f"code has {rules.RULES_VERSION}; rebuild the package")
            from catboost import CatBoostRegressor

            model = CatBoostRegressor()
            model.load_model(str(path / "model.cbm"))
            read = lambda name: json.loads((path / name).read_text(encoding="utf-8"))   # noqa: E731
            calibration_payload = read("interval_calibration.json")
            return cls(directory=path, manifest=manifest, model=model,
                       preprocessor=tc.Preprocessor.from_json(read("preprocessing.json")),
                       calibration=iv.IntervalCalibration.from_json(calibration_payload),
                       gate=iv.ServingGate.from_json(calibration_payload["serving_gate"]),
                       district_support=rules.DistrictSupport.from_json(read("district_support.json")))
        except PackageError:
            raise
        except Exception as error:                       # corrupt JSON, catboost failure, missing keys, ...
            raise PackageError(f"cannot load package {path}: {error}") from error

    @property
    def versions(self) -> Dict[str, str]:
        return {"model_version": self.manifest["model_version"],
                "rule_engine_version": rules.RULE_ENGINE_VERSION}

    def provenance(self) -> Dict[str, Any]:
        m = self.manifest
        return {"interface_version": INFERENCE_INTERFACE_VERSION, "package_version": m["package_version"],
                "calibration_version": m["calibration_version"], "rules_version": rules.RULES_VERSION,
                "geography_version": m.get("geography_version"), "dataset_version": m.get("dataset_version"),
                "snapshot_sha256": m.get("snapshot_sha256"), "model_data_as_of": m.get("data_as_of"),
                "evidence_level": m.get("evidence_level"), "temporal_split": m.get("temporal_split"),
                "is_synthetic": m.get("is_synthetic"), "coverage_version": COVERAGE_VERSION,
                "fallback": None, "interval_withheld_reasons": []}


_DEFAULT: Dict[str, Any] = {"package": None, "error": None, "path": None}


def load_package(directory: Any = None) -> InferencePackage:
    """Load ``directory`` (default: ``$FAIRRENT_MODEL_PACKAGE``). Raises ``PackageError``."""
    target = directory or os.environ.get(PACKAGE_ENV_VAR)
    if not target:
        raise PackageError(f"no package directory given and ${PACKAGE_ENV_VAR} is not set")
    return InferencePackage.load(target)


def _default_package() -> Optional[InferencePackage]:
    """Process-wide package for callers that do not pass one; load failures are remembered, not retried per request."""
    target = os.environ.get(PACKAGE_ENV_VAR)
    if _DEFAULT["path"] != target:
        _DEFAULT.update(package=None, error=None, path=target)
        try:
            _DEFAULT["package"] = load_package(target)
        except PackageError as error:
            LOGGER.error("B07 package unavailable, serving abstentions: %s", error)
            _DEFAULT["error"] = str(error)
    return _DEFAULT["package"]


# ------------------------------------------------------------------------------ assess

_NO_INTERVAL = {**iv.null_interval(), "calibration_version": None}


def _money(value: float) -> str:
    return f"${value:,.2f}"


def _response(inp: Mapping[str, Any], *, versions: Mapping[str, str], status: str, tier: str,
              estimate: Optional[float], per_sqm: Optional[float], deviation: Optional[float],
              observed: Mapping[str, Any], interval: Optional[Mapping[str, Any]], attributions: Sequence[Any],
              area_reference: Optional[Mapping[str, Any]], explanation: str, ontology: Optional[Mapping[str, Any]],
              provenance: Mapping[str, Any]) -> Dict[str, Any]:
    return {"coordinates": {"latitude": inp["latitude"], "longitude": inp["longitude"]},
            "versions": dict(versions),
            "valuation_assessment": {"estimated_price_usd": estimate, "price_per_sqm_usd": per_sqm,
                                     "valuation_tier": tier, "assessment_status": status,
                                     "deviation_from_baseline_pct": deviation},
            "observed_market_statistics": dict(observed),
            "ml_prediction_interval": dict(interval or _NO_INTERVAL),
            "feature_attributions": list(attributions),
            "area_reference": dict(area_reference) if area_reference else None,
            "explanation": explanation, "ontology": dict(ontology) if ontology else None,
            "provenance": dict(provenance)}


def _abstain(inp: Mapping[str, Any], package: Optional[InferencePackage], observed: Mapping[str, Any],
             reason_code: str, explanation: str, *, provenance: Optional[Dict[str, Any]] = None,
             area_reference: Optional[Mapping[str, Any]] = None,
             ontology: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    prov = provenance if provenance is not None else (package.provenance() if package else {
        "interface_version": INFERENCE_INTERFACE_VERSION, "package_version": None, "rules_version": rules.RULES_VERSION,
        "coverage_version": COVERAGE_VERSION, "fallback": None, "interval_withheld_reasons": []})
    prov["abstention_reason"] = reason_code
    versions = package.versions if package else {"model_version": "unavailable",
                                                 "rule_engine_version": rules.RULE_ENGINE_VERSION}
    return _response(inp, versions=versions, status=STATUS_ABSTAIN, tier="UNCERTAIN_OUTOF_SCOPE", estimate=None,
                     per_sqm=None, deviation=None, observed=observed, interval=None, attributions=[],
                     area_reference=area_reference, explanation=explanation, ontology=ontology, provenance=prov)


def _area_reference(package: Optional[InferencePackage], district_label: Optional[str]) -> Optional[Dict[str, Any]]:
    if package is None:
        return None
    pre = package.preprocessor
    area = pre.district_area.get(district_label) if district_label else None
    area = pre.global_area if area is None else area
    return {"district": rules._district_id(district_label) if district_label else None,
            "reference_area_sqm": round(float(area), 2),
            "note": "Training-fitted reference area; not the requested apartment area."}


def assess(model_input: Mapping[str, Any], *, comparables: Optional[Sequence[Mapping[str, Any]]] = None,
           package: Optional[InferencePackage] = None, now: Optional[datetime] = None) -> Dict[str, Any]:
    """The one inference entry point. See the module docstring for the contract and failure behaviour."""
    inp = validate_model_input(model_input)
    check_coverage(inp["latitude"], inp["longitude"])
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    observed = observed_statistics(comparables, as_of=parse_utc(inp["as_of"]), now=now)
    if package is None:
        package = _default_package()
        if package is None:
            return _abstain(inp, None, observed, "model_unavailable",
                            "The valuation model is not available; only observed market statistics can be shown.",
                            provenance={"interface_version": INFERENCE_INTERFACE_VERSION, "package_version": None,
                                        "rules_version": rules.RULES_VERSION, "coverage_version": COVERAGE_VERSION,
                                        "fallback": _DEFAULT["error"] or "package not loaded",
                                        "interval_withheld_reasons": []})
    try:
        return _assess_with_package(inp, comparables, package, observed, now)
    except InferenceError:
        raise
    except Exception as error:                              # model/gate/SHAP failure must not take the API down
        LOGGER.exception("B07 inference failed; returning an abstention")
        prov = package.provenance()
        prov["fallback"] = f"inference_error: {type(error).__name__}"
        return _abstain(inp, package, observed, "inference_error",
                        "The valuation model failed for this request; only observed market statistics can be shown.",
                        provenance=prov)


def _assess_with_package(inp: Dict[str, Any], comparables: Optional[Sequence[Mapping[str, Any]]],
                         package: InferencePackage, observed: Mapping[str, Any], now: datetime) -> Dict[str, Any]:
    prov = package.provenance()
    label = _district_label(inp["district"])
    full = _with_distances(inp)
    ref = _area_reference(package, label)
    age = observed["data_freshness_days"]

    # 1. observed evidence too thin or too old -> abstain (contract rule; observed statistics stay visible)
    if observed["insufficient_data"]:
        if age is None or age > MAX_SOURCE_AGE_DAYS:
            why = f"The source snapshot is {age} days old (limit {MAX_SOURCE_AGE_DAYS})."
        else:
            why = (f"Only {observed['comparables_count']} comparable listing(s) in the cohort "
                   f"(minimum {MIN_COMPARABLES}).")
        return _abstain(inp, package, observed, "insufficient_observed_data", why + " Valuation unavailable.",
                        provenance=prov, area_reference=ref)

    mean = observed["cluster_mean_price_usd"]
    # 2. area or rooms unknown -> observed baseline only; no model prediction, no interval
    if full["area_sqm"] is None or full["rooms"] is None:
        per_sqm = observed["cluster_mean_price_per_sqm_usd"]
        text = ("Area reference only; property characteristics were not provided. The figure shown is the observed "
                "cohort mean, not a prediction for a specific apartment, and no interval is available.")
        return _response(inp, versions=package.versions, status=STATUS_BASELINE, tier="Baseline Market Estimate",
                         estimate=mean, per_sqm=per_sqm, deviation=0.0, observed=observed, interval=None,
                         attributions=[], area_reference=ref, explanation=text, ontology=None, provenance=prov)

    # 3. model prediction, then the serving gate
    row = {"latitude": full["latitude"], "longitude": full["longitude"], "area_sqm": full["area_sqm"],
           "rooms": full["rooms"], "floor": full["floor"], "total_floors": full["total_floors"],
           "distance_metro_m": full["distance_metro_m"], "distance_center_m": full["distance_center_m"],
           "distance_university_m": full["distance_university_m"], "district": label,
           "building_type": full["building_type"], "utilities_included": None}
    frame = pd.DataFrame([row])
    prediction = float(tc.predict_usd(package.model, package.preprocessor, frame)[0])
    reasons = package.gate.reasons(frame)[0] + iv.prediction_reasons(prediction)[0]
    prov["interval_withheld_reasons"] = list(reasons)
    if reasons:
        return _abstain(inp, package, observed, "serving_gate",
                        "No supported estimate for this property (" + ", ".join(reasons) + "); the model would be "
                        "extrapolating. Observed market statistics remain available.", provenance=prov,
                        area_reference=ref)
    interval = iv.prediction_interval(prediction, package.calibration, reasons=reasons)
    estimate = round(prediction, 2)
    per_sqm = round(estimate / full["area_sqm"], 2)
    deviation = round((estimate - mean) / mean * 100.0, 2)

    # 4. learned effects (SHAP) and B06 rule explanation, kept separate
    x = package.preprocessor.transform(frame)[package.preprocessor.feature_names]
    learned = attr.explain_with_catboost(package.model, x, cat_features=tc.CATEGORICAL_FEATURES)
    ontology_input = {**full, "district": inp["district"], "coordinate_confidence": "approximate"}
    ontology = rules.explain_valuation(ontology_input, district_support=package.district_support,
                                       learned_attributions=learned)
    level = int(round(100 * interval["confidence_level"]))
    text = (f"Estimated monthly asking rent {_money(estimate)} (calibrated {level}% interval "
            f"{_money(interval['lower_bound_usd'])}-{_money(interval['upper_bound_usd'])}), "
            f"{deviation:+.1f}% versus the observed cohort mean. Asking prices are not signed rents. "
            + ontology["text"])
    return _response(inp, versions=package.versions, status=STATUS_SUCCESS, tier="Model estimate", estimate=estimate,
                     per_sqm=per_sqm, deviation=deviation, observed=observed, interval=interval,
                     attributions=learned, area_reference=None, explanation=text, ontology=ontology, provenance=prov)


def kind_for(assessment: Mapping[str, Any]) -> str:
    """Public ``kind`` for the backend: a property valuation only when the model produced an estimate."""
    status = assessment["valuation_assessment"]["assessment_status"]
    return "property_valuation" if status == STATUS_SUCCESS else "area_reference"


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run one assessment from a JSON file with model_input and comparables.")
    parser.add_argument("--package", type=Path)
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args(argv)
    payload = json.loads(args.request.read_text(encoding="utf-8"))
    try:
        package = load_package(args.package) if args.package else None
        result = assess(payload["model_input"], comparables=payload.get("comparables"), package=package)
    except InferenceError as error:
        print(json.dumps({"error": type(error).__name__, "message": str(error)}))
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
