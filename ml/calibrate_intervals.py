"""[B05] Calibrate prediction intervals for a trained B04 model and evaluate them.

    python -m ml.calibrate_intervals \\
        --b04 artifacts/b04/b04-v1.0.0 --snapshot data/processed/v1.0.0 --version b05-v1.0.0

Rules (see docs/B05-interval-calibration.md):
  * calibration uses ONLY the validation split (rows that pass the serving gate); test labels
    are never used to fit, choose or tune anything -- the test split is only scored;
  * the interval method is fixed in advance (``relative`` split conformal, ``--method`` to
    override); the other methods are reported for comparison and never selected from test results;
  * the serving gate (coordinate-only, area out of range, sparse local data) is fitted on the
    training split only and its rules are fixed in advance;
  * the B04 artifact checksums and the snapshot SHA-256 are verified before anything is used,
    and the calibration records the model SHA-256 it belongs to.

Artifacts go to ``artifacts/b05/<version>/`` (git-ignored).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from ml import intervals as iv
from ml import train_compare as tc

EXPERIMENT_SCHEMA_VERSION = "b05-experiment-v1"
COVERAGE_TARGET = 0.92       # ml/CONTRACT.md 4.C: nominal 95% interval must cover >= 92% (provisional)
WIDTH_RATIO_TARGET = 0.22    # ml/CONTRACT.md 4.C: interval width / predicted price <= 0.22 (provisional)
SMALL_SAMPLE = 30
OPTIONAL_FEATURES = ["rooms", "floor", "total_floors", "distance_metro_m", "distance_university_m",
                     "utilities_included", "building_type"]
MISSING_SCENARIOS = {
    "rooms_missing": ["rooms"],
    "floors_missing": ["floor", "total_floors"],
    "landmark_distances_missing": ["distance_metro_m", "distance_university_m"],
    "all_optional_missing": OPTIONAL_FEATURES,
    "area_missing": ["area_sqm"],
}


class ArtifactError(RuntimeError):
    """B04 artifacts are missing, altered or do not match the snapshot."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_b04(b04_dir: Path) -> Tuple[dict, tc.Preprocessor, Any, str]:
    """Verify B04 checksums, then load metadata, the frozen preprocessor and the CatBoost model."""
    from catboost import CatBoostRegressor

    sums_path = b04_dir / "SHA256SUMS.json"
    if not sums_path.is_file():
        raise ArtifactError(f"{sums_path} not found; is --b04 a B04 artifact directory?")
    for name, digest in json.loads(sums_path.read_text(encoding="utf-8")).items():
        path = b04_dir / name
        if not path.is_file() or _sha256(path) != digest:
            raise ArtifactError(f"B04 artifact {name} is missing or does not match SHA256SUMS.json")
    meta = json.loads((b04_dir / "metadata.json").read_text(encoding="utf-8"))
    pre = tc.Preprocessor.from_json(json.loads((b04_dir / "preprocessing.json").read_text(encoding="utf-8")))
    model = CatBoostRegressor()
    model.load_model(str(b04_dir / "model.cbm"))
    return meta, pre, model, _sha256(b04_dir / "model.cbm")


def check_snapshot_matches(meta: dict, splits: Dict[str, pd.DataFrame], manifest: dict) -> None:
    """Calibrating against a different snapshot than the model was trained on would void the guarantee."""
    trained = meta.get("dataset", {})
    if trained.get("snapshot_sha256") != manifest.get("snapshot_sha256"):
        raise ArtifactError(
            "snapshot SHA-256 differs from the one B04 trained on "
            f"({trained.get('snapshot_sha256')} vs {manifest.get('snapshot_sha256')}); use the same snapshot")
    rows = {k: int(len(v)) for k, v in splits.items()}
    if trained.get("split_rows") != rows:
        raise ArtifactError(f"split sizes {rows} differ from B04's {trained.get('split_rows')}")


def _status_counts(values: List[str]) -> Dict[str, int]:
    return {s: int(sum(v == s for v in values)) for s in iv.PRICE_STATUSES}


def _mask(frame: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    out = frame.copy()
    for column in columns:
        if column in out.columns:
            out[column] = np.nan if pd.api.types.is_numeric_dtype(out[column]) else None
    return out


def _metrics(y: np.ndarray, pred: np.ndarray, cal: iv.IntervalCalibration, level: float,
             mask: Optional[np.ndarray] = None, groups: Optional[np.ndarray] = None) -> Dict[str, Any]:
    if mask is None:
        mask = np.ones(len(y), bool)
    if not mask.any():
        return iv.interval_metrics([], [], [], [])
    lo, hi = _bounds(cal, pred[mask], level, None if groups is None else groups[mask])
    return iv.interval_metrics(y[mask], pred[mask], lo, hi)


def _bounds(cal: iv.IntervalCalibration, pred: np.ndarray, level: float,
            groups: Optional[np.ndarray]) -> Tuple[np.ndarray, np.ndarray]:
    if cal.method != "relative_by_district" or groups is None:
        return cal.bounds(pred, level)
    lo = np.empty(len(pred))
    hi = np.empty(len(pred))
    for i, (p, g) in enumerate(zip(pred, groups)):
        lower, upper = cal.bounds(float(p), level, str(g))
        lo[i], hi[i] = lower[0], upper[0]
    return lo, hi


def _district_labels(frame: pd.DataFrame) -> np.ndarray:
    return np.asarray(["unresolved" if not isinstance(d, str) else d for d in frame["district"]])


def _conditional(y: np.ndarray, pred: np.ndarray, cal: iv.IntervalCalibration, level: float,
                 served: np.ndarray, keys: np.ndarray, order: Optional[List[str]] = None) -> List[dict]:
    rows = []
    for key in (order or sorted(set(keys[served]))):
        sel = served & (keys == key)
        m = _metrics(y, pred, cal, level, sel)
        m.update({"group": str(key), "small_sample_warning": m["n"] < SMALL_SAMPLE})
        rows.append(m)
    return rows


def run(args: argparse.Namespace) -> dict:
    b04_dir = Path(args.b04)
    meta04, pre, model, model_sha = load_b04(b04_dir)
    splits, manifest = tc.load_snapshot(Path(args.snapshot))
    check_snapshot_matches(meta04, splits, manifest)
    train, val, test = splits["train"], splits["validation"], splits["test"]
    if len(val) == 0 or len(test) == 0:
        raise ArtifactError("validation and test splits must be non-empty")
    temporal = bool((manifest.get("split_policy") or {}).get("temporal", True))

    y_val, y_test = val["price_usd"].to_numpy(float), test["price_usd"].to_numpy(float)
    p_val, p_test = tc.predict_usd(model, pre, val), tc.predict_usd(model, pre, test)

    gate = iv.ServingGate.fit(train)
    val_reasons, test_reasons = gate.reasons(val), gate.reasons(test)
    val_served = np.array([not r for r in val_reasons])
    test_served = np.array([not r for r in test_reasons])
    if val_served.sum() == 0:
        raise iv.CalibrationError("no validation rows pass the serving gate")

    levels = tuple(iv.DEFAULT_LEVELS)
    primary = args.level
    if primary not in levels:
        raise SystemExit(f"--level must be one of {levels}")
    val_dist, test_dist = _district_labels(val), _district_labels(test)

    def calibrate(method: str) -> iv.IntervalCalibration:
        return iv.fit_calibration(
            y_val[val_served], p_val[val_served], method=method, groups=val_dist[val_served], levels=levels,
            primary_level=primary, calibration_version=f"{args.version}-{method}",
            meta={"calibration_split": "validation (rows passing the serving gate)",
                  "n_validation_total": int(len(val)), "n_validation_served": int(val_served.sum()),
                  "b04_model_version": meta04.get("model_version"), "b04_model_sha256": model_sha,
                  "snapshot_sha256": manifest.get("snapshot_sha256"),
                  "dataset_version": manifest.get("dataset_version"), "temporal_split": temporal,
                  "gate_reason_counts_validation": _reason_counts(val_reasons)})

    cal = calibrate(args.method)
    groups_for = test_dist if args.method == "relative_by_district" else None

    # ---- held-out coverage and width (test labels are only scored here) ----
    held_out = {lv: {"served_rows": _metrics(y_test, p_test, cal, lv, test_served, groups_for),
                     "all_rows_if_intervals_were_always_returned": _metrics(y_test, p_test, cal, lv, None, groups_for)}
                for lv in levels}
    abstained = ~test_served
    abstain_report = {
        "n": int(abstained.sum()), "share": round(float(abstained.mean()), 4),
        "reason_counts": _reason_counts(test_reasons),
        "coverage_if_served_anyway": _metrics(y_test, p_test, cal, primary, abstained, groups_for),
        "note": "These rows return null interval fields and price_status=insufficient_data.",
    }
    variants = {}
    for method in iv.METHODS:
        other = calibrate(method)
        g = test_dist if method == "relative_by_district" else None
        variants[method] = {level_key: _metrics(y_test, p_test, other, lv, test_served, g)
                            for level_key, lv in ((iv.level_key(lv), lv) for lv in levels)}
    variants["note"] = (f"Primary method '{args.method}' was fixed before looking at test results; the others "
                        "are reported for comparison and were not used to choose it.")

    # ---- conditional coverage (primary method and level, served rows) ----
    quart = np.quantile(p_val[val_served], [0.25, 0.5, 0.75])
    tier = np.asarray([f"Q{int(np.searchsorted(quart, p, side='right')) + 1}" for p in p_test])
    area_test = pd.to_numeric(test["area_sqm"], errors="coerce").to_numpy(float)
    area_val = pd.to_numeric(val["area_sqm"], errors="coerce").to_numpy(float)[val_served]
    area_cuts = np.nanquantile(area_val, [0.25, 0.5, 0.75, 0.95])
    area_bin = np.asarray(["unknown" if not np.isfinite(a) else
                           ("top5pct" if a >= area_cuts[3] else f"Q{int(np.searchsorted(area_cuts[:3], a, side='right')) + 1}")
                           for a in area_test])
    conditional = {
        "level": primary,
        "by_district": _conditional(y_test, p_test, cal, primary, test_served, test_dist),
        "by_predicted_price_quartile": _conditional(y_test, p_test, cal, primary, test_served, tier, ["Q1", "Q2", "Q3", "Q4"]),
        "by_area_bin": _conditional(y_test, p_test, cal, primary, test_served, area_bin,
                                    [b for b in ["Q1", "Q2", "Q3", "Q4", "top5pct"] if (test_served & (area_bin == b)).any()]),
        "price_quartile_cutpoints_usd": [round(float(c), 2) for c in quart],
        "area_bin_cutpoints_sqm": [round(float(c), 1) for c in area_cuts],
    }
    covs = [r["coverage"] for r in conditional["by_district"] if not r["small_sample_warning"] and r["coverage"] is not None]
    conditional["worst_district_coverage_n_ge_30"] = round(min(covs), 4) if covs else None

    # ---- scenarios: sparse / missing-feature / out-of-distribution ----
    base_cov = held_out[primary]["served_rows"]
    sparse_only = np.array([r == [iv.REASON_SPARSE] for r in test_reasons])
    area_oor = np.array([iv.REASON_AREA_RANGE in r for r in test_reasons])
    scenarios: Dict[str, Any] = {
        "sparse_local_data": {
            "rule": f"< {gate.min_local_train} training listings in the 3x3 grid block ({gate.cell_size_deg} deg cells)",
            "test_rows_flagged": int(sum(iv.REASON_SPARSE in r for r in test_reasons)),
            "coverage_if_served_anyway": _metrics(y_test, p_test, cal, primary, sparse_only, groups_for),
        },
        "out_of_distribution": {
            "natural_area_outside_training_range": {
                "rule": f"area_sqm outside [{gate.area_min:.1f}, {gate.area_max:.1f}] (train quantiles {list(gate.area_quantiles)})",
                "n": int(area_oor.sum()),
                "coverage_if_served_anyway": _metrics(y_test, p_test, cal, primary, area_oor, groups_for),
            },
        },
        "missing_features": {},
    }
    unmasked_mae = float(np.abs(p_test[test_served] - y_test[test_served]).mean())
    for name, columns in MISSING_SCENARIOS.items():
        masked = _mask(test, columns)
        pm = tc.predict_usd(model, pre, masked)
        reasons_masked = gate.reasons(masked)
        served_masked = np.array([not r for r in reasons_masked])
        m = _metrics(y_test, pm, cal, primary, test_served, groups_for)
        scenarios["missing_features"][name] = {
            "columns_blanked": columns, "n_rows": int(test_served.sum()),
            "interval_still_returned_share": round(float((served_masked & test_served).sum() / max(test_served.sum(), 1)), 4),
            "coverage_if_interval_were_returned": m["coverage"], "median_width_ratio": m["median_width_ratio"],
            "mae_usd": round(float(np.abs(pm[test_served] - y_test[test_served]).mean()), 2),
            "mae_usd_unmasked": round(unmasked_mae, 2),
            "coverage_change_vs_unmasked": (None if m["coverage"] is None or base_cov["coverage"] is None
                                           else round(m["coverage"] - base_cov["coverage"], 4)),
        }
    shifted = test.copy()
    shifted["latitude"] = pd.to_numeric(shifted["latitude"], errors="coerce") + 0.30
    huge = test.copy()
    huge["area_sqm"] = gate.area_max * 2
    scenarios["out_of_distribution"]["synthetic_location_shifted_0.3deg_north"] = {
        "share_withheld": round(float(np.mean([bool(r) for r in gate.reasons(shifted)])), 4)}
    scenarios["out_of_distribution"]["synthetic_area_twice_training_maximum"] = {
        "share_withheld": round(float(np.mean([bool(r) for r in gate.reasons(huge)])), 4)}

    # ---- price_status consistency ----
    lo_t, hi_t = _bounds(cal, p_test, primary, groups_for)
    blocks = [iv.prediction_interval(float(p), cal, level=primary, group=(str(g) if groups_for is not None else None),
                                     reasons=r) for p, g, r in zip(p_test, test_dist, test_reasons)]
    checks = {
        "asking_price_equals_true_price": _status_counts([iv.price_status(a, b) for a, b in zip(y_test, blocks)]),
        "asking_price_x2_of_prediction": _status_counts([iv.price_status(2.0 * p, b) for p, b in zip(p_test, blocks)]),
        "asking_price_x0.25_of_prediction": _status_counts([iv.price_status(0.25 * p, b) for p, b in zip(p_test, blocks)]),
        "missing_asking_price": _status_counts([iv.price_status(None, b) for b in blocks]),
        "bounds_enclose_prediction": bool(all(b["lower_bound_usd"] <= p <= b["upper_bound_usd"]
                                              for p, b in zip(p_test, blocks) if b["lower_bound_usd"] is not None)),
        "width_equals_upper_minus_lower": bool(all(
            abs(b["interval_width_usd"] - (b["upper_bound_usd"] - b["lower_bound_usd"])) < 1e-9
            for b in blocks if b["lower_bound_usd"] is not None)),
        "withheld_blocks_are_all_null": bool(all(set(b.values()) == {None} for b, s in zip(blocks, test_served) if not s)),
    }
    within_true = checks["asking_price_equals_true_price"]["within_range"]
    served_n = int(test_served.sum())
    checks["within_range_share_of_served_at_true_price"] = round(within_true / served_n, 4) if served_n else None

    val_mae, test_mae = float(np.abs(p_val - y_val).mean()), float(np.abs(p_test - y_test).mean())
    val_med, test_med = float(np.median(np.abs(p_val - y_val))), float(np.median(np.abs(p_test - y_test)))
    primary_metrics = held_out[primary]["served_rows"]
    targets = {
        "coverage_target": {"value": COVERAGE_TARGET, "applies_to_nominal": 0.95,
                            "observed_at_nominal_0.95": held_out[0.95]["served_rows"]["coverage"],
                            "met": (held_out[0.95]["served_rows"]["coverage"] or 0) >= COVERAGE_TARGET},
        "width_ratio_target": {"value": WIDTH_RATIO_TARGET,
                               "observed_median_width_ratio_at_0.95": held_out[0.95]["served_rows"]["median_width_ratio"],
                               "met": (held_out[0.95]["served_rows"]["median_width_ratio"] or 9) <= WIDTH_RATIO_TARGET},
        "note": "Provisional targets from ml/CONTRACT.md 4.C; reported against, not used to tune anything.",
    }
    report = {
        "metadata": {
            "experiment_schema_version": EXPERIMENT_SCHEMA_VERSION, "version": args.version,
            "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "method": args.method, "primary_level": primary, "levels": list(levels),
            "b04_model_version": meta04.get("model_version"), "b04_model_sha256": model_sha,
            "snapshot_sha256": manifest.get("snapshot_sha256"), "dataset_version": manifest.get("dataset_version"),
            "temporal_split": temporal, "evidence_level": meta04.get("evidence_level"),
            "calibration_rows": cal.n_calibration, "split_rows": {k: int(len(v)) for k, v in splits.items()},
        },
        "calibration": {"quantiles": cal.levels, "n_calibration": cal.n_calibration,
                        "n_validation_total": int(len(val)), "group_sizes": cal.group_sizes,
                        "districts_with_own_quantile": sorted(cal.group_levels),
                        "validation_mae_usd": round(val_mae, 2), "test_mae_usd": round(test_mae, 2),
                        "test_to_validation_mae_ratio": round(test_mae / val_mae, 4),
                        "validation_median_ae_usd": round(val_med, 2), "test_median_ae_usd": round(test_med, 2),
                        "test_to_validation_median_ae_ratio": round(test_med / val_med, 4),
                        "note": ("A ratio well above 1 means the validation residuals used for calibration were "
                                 "smaller than test residuals (early-stopping optimism or heavy-tailed outliers; the "
                                 "median ratio is robust to outliers).")},
        "held_out_test": {iv.level_key(lv): v for lv, v in held_out.items()},
        "abstention": abstain_report,
        "variants_compared_on_test": variants,
        "conditional_coverage": conditional,
        "scenarios": scenarios,
        "price_status_checks": checks,
        "targets_vs_results": targets,
        "limitations": _limitations(temporal, conditional, primary_metrics, abstain_report, scenarios, cal),
    }

    out = Path(args.output_dir) / args.version
    out.mkdir(parents=True, exist_ok=True)
    payload = cal.to_json()
    payload["serving_gate"] = gate.to_json()
    (out / "interval_calibration.json").write_text(iv.dumps(payload), encoding="utf-8")
    (out / "b05_report.json").write_text(iv.dumps(report), encoding="utf-8")
    digest = {p.name: _sha256(p) for p in sorted(out.iterdir()) if p.name != "SHA256SUMS.json"}
    (out / "SHA256SUMS.json").write_text(json.dumps(digest, indent=2), encoding="utf-8")
    report["artifact_dir"] = str(out)
    return report


def _reason_counts(reasons: List[List[str]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in reasons:
        for reason in row:
            counts[reason] = counts.get(reason, 0) + 1
    counts["rows_withheld"] = int(sum(bool(r) for r in reasons))
    return dict(sorted(counts.items()))


def _limitations(temporal: bool, conditional: dict, primary_metrics: dict, abstain: dict,
                 scenarios: dict, cal: iv.IntervalCalibration) -> List[str]:
    notes = [
        "Intervals describe the ASKING price of listings, not what tenants finally pay.",
        "Coverage is a marginal average over served rows under exchangeability of calibration and "
        "serving rows. It is not a guarantee for any single listing, district or price level; see "
        "conditional_coverage for the observed spread.",
        "Calibration reuses the validation split that B04 used for CatBoost early stopping, so "
        "validation residuals can be slightly optimistic; compare test_to_validation_median_ae_ratio.",
        "Reposts and identical units in one building were merged for splitting, but listings from the "
        "same tower can still sit in calibration and test, which makes in-sample coverage optimistic.",
        "Intervals are withheld for coordinate-only requests, areas outside the training range and "
        "sparse locations; they are not calibrated for those cases and must not be replaced by an "
        "observed standard deviation.",
        "Blanking optional inputs keeps the same quantile, but the true error grows; see "
        "scenarios.missing_features for the coverage drop before relying on sparse requests.",
        "Width is large relative to price because rents are noisy given the available features "
        "(no renovation or building-type data); the provisional width target is reported, not met by tuning.",
    ]
    if not temporal:
        notes.insert(0, "The split is NOT chronological (one-date scrape), so coverage is measured on a random "
                        "duplicate-group-isolated sample of the same period. Future listings will be drawn from a "
                        "shifted market and real coverage can be lower. Re-calibrate on a chronological split.")
    if cal.method == "relative_by_district":
        notes.append("Districts with fewer than min_group_size calibration rows use the global quantile.")
    return notes


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--b04", required=True, help="B04 artifact directory (artifacts/b04/<version>)")
    ap.add_argument("--snapshot", required=True, help="the SAME A06 snapshot directory B04 trained on")
    ap.add_argument("--version", required=True)
    ap.add_argument("--method", choices=iv.METHODS, default="relative")
    ap.add_argument("--level", type=float, default=iv.PRIMARY_LEVEL, help="primary nominal level (0.80, 0.90 or 0.95)")
    ap.add_argument("--output-dir", default="artifacts/b05")
    rep = run(ap.parse_args(argv))
    m = rep["held_out_test"][iv.level_key(rep["metadata"]["primary_level"])]["served_rows"]
    t = rep["targets_vs_results"]
    print(f"method={rep['metadata']['method']}  level={rep['metadata']['primary_level']}  "
          f"calibration rows={rep['calibration']['n_calibration']}")
    print(f"held-out test (served rows, n={m['n']}): coverage={m['coverage']}  median width=${m['median_width_usd']} "
          f"(ratio {m['median_width_ratio']})")
    print(f"coverage target >= {COVERAGE_TARGET} at 0.95: {t['coverage_target']['observed_at_nominal_0.95']} "
          f"-> {'met' if t['coverage_target']['met'] else 'NOT met'};  width-ratio target <= {WIDTH_RATIO_TARGET}: "
          f"{t['width_ratio_target']['observed_median_width_ratio_at_0.95']} -> "
          f"{'met' if t['width_ratio_target']['met'] else 'NOT met'}")
    a = rep["abstention"]
    print(f"withheld (no interval): {a['n']} rows ({a['share']:.1%})  reasons={a['reason_counts']}")
    if not rep["metadata"]["temporal_split"]:
        print("WARNING: non-temporal split; coverage is an in-time estimate (see report 'limitations').")
    print("artifacts:", rep["artifact_dir"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
