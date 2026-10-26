"""[B04] Train a CatBoost rental-price model and compare it with the B03 baseline.

Usage (real data, an A06 snapshot directory with train/validation/test CSVs):

    python -m ml.train_compare --snapshot data/processed/v1.0.0 --version b04-v1.0.0

Usage (pipeline smoke test only; synthetic data, results are NOT findings):

    python -m ml.train_compare --synthetic --version b04-synthetic-demo

Fairness rules (ml/CONTRACT.md section 3):
  * the split comes from the A06 export unchanged (chronological, duplicate-group isolated);
  * imputation values, the baseline's comparable pool and the fallback statistics are
    fitted on the training split only;
  * the validation split is used only for CatBoost early stopping;
  * the test split is scored once, after all choices are made.

Artifacts go to ``artifacts/b04/<version>/`` (git-ignored). Nothing here touches the
database or any existing module.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from ml.baseline import ComparableMedianBaseline

EXPERIMENT_SCHEMA_VERSION = "b04-v1"
SEED = 20261026

NUMERIC_FEATURES = [
    "latitude", "longitude", "area_sqm", "rooms", "floor", "total_floors",
    "distance_metro_m", "distance_center_m", "distance_university_m",
]
CATEGORICAL_FEATURES = ["district", "building_type", "utilities_included"]
# `renovation` is always null in the A06 export (no verified source mapping), so it carries
# no signal and is deliberately not a model input until a source exists.
EXCLUDED_FEATURES = {
    "renovation": "always null in A06 export; constant column",
    "price_usd": "target",
    "original_price": "derived from the target",
    "exchange_rate": "conversion provenance, derived from the target",
    "dedup_group_id": "split-isolation key only",
    "observation_date": "split key only",
    "observation_at": "split key only",
    "first_seen_at": "split key only",
}
MISSING_INDICATORS = ["area_sqm", "rooms", "distance_metro_m", "distance_university_m"]
FALLBACK_AREA_SQM = 60.0  # same reference area as the B03 baseline default
NO_LANDMARK_M = 99999.0   # CONTRACT.md imputation for missing metro/university distance

CATBOOST_PARAMS = {
    "loss_function": "MAE",
    "eval_metric": "MAE",
    "iterations": 3000,
    "learning_rate": 0.05,
    "depth": 6,
    "l2_leaf_reg": 5.0,
    "random_seed": SEED,
    "early_stopping_rounds": 200,
    "thread_count": 1,          # single thread keeps runs bit-reproducible
    "allow_writing_files": False,
    "verbose": False,
}


# --------------------------------------------------------------------------- data


def synthetic_snapshot(n_groups: int = 1500, seed: int = SEED) -> Dict[str, pd.DataFrame]:
    """Synthetic A06-shaped splits. For exercising the pipeline only."""
    rng = np.random.default_rng(seed)
    districts = {
        "Kentron": (40.1811, 44.5136, 15.5), "Arabkir": (40.2010, 44.5080, 12.5),
        "Shengavit": (40.1450, 44.4850, 8.5), "Malatia-Sebastia": (40.1700, 44.4500, 8.0),
        "Nor Nork": (40.1900, 44.5700, 9.0),
    }
    names = list(districts)
    start = pd.Timestamp("2026-04-01")
    rows = []
    for g in range(n_groups):
        d = names[rng.integers(len(names))]
        lat0, lon0, ppsqm = districts[d]
        lat, lon = lat0 + rng.normal(0, 0.008), lon0 + rng.normal(0, 0.008)
        area = float(np.clip(rng.normal(62, 22), 18, 220))
        rooms = int(np.clip(round(area / 28 + rng.normal(0, 0.5)), 1, 6))
        center = math.hypot((lat - 40.1776) * 111000, (lon - 44.5126) * 85000)
        metro = float(abs(rng.normal(900, 600)))
        uni = float(abs(rng.normal(1500, 900)))
        price_core = area * ppsqm * (1 - 0.00004 * min(center, 6000)) * (1 + 0.1 * (metro < 500))
        anchor = start + pd.Timedelta(days=int(rng.integers(0, 200)))
        btype = rng.choice(["stone", "monolith", "panel", None], p=[0.4, 0.3, 0.2, 0.1])
        total_floors = int(rng.integers(4, 18))
        floor = int(rng.integers(1, total_floors + 1))
        for k in range(1 + int(rng.random() < 0.25) * int(rng.integers(1, 3))):
            obs = anchor + pd.Timedelta(days=int(rng.integers(0, 6)) * k)
            price = max(80.0, price_core * float(np.exp(rng.normal(0, 0.12))))
            if rng.random() < 0.01:
                price *= 4  # a few gross outliers to exercise the error investigation
            rows.append({
                "observation_date": obs.date().isoformat(), "observation_at": obs.isoformat() + "Z",
                "first_seen_at": anchor.isoformat() + "Z",
                "dedup_group_id": hashlib.sha256(f"syn-{g}".encode()).hexdigest(),
                "price_usd": round(price, 2), "latitude": lat, "longitude": lon,
                "area_sqm": None if rng.random() < 0.12 else round(area, 1),
                "rooms": None if rng.random() < 0.08 else rooms,
                "building_type": btype, "floor": floor, "total_floors": total_floors,
                "renovation": None, "district": d,
                "distance_metro_m": None if rng.random() < 0.05 else metro,
                "distance_center_m": center,
                "distance_university_m": None if rng.random() < 0.05 else uni,
                "utilities_included": rng.choice([True, False, None]),
                "source": "synthetic",
            })
    frame = pd.DataFrame(rows)
    frame["_anchor"] = frame.groupby("dedup_group_id")["observation_date"].transform("min")
    anchors = sorted(frame["_anchor"].unique())
    train_end, val_end = anchors[int(len(anchors) * 0.70) - 1], anchors[int(len(anchors) * 0.85) - 1]
    out = {}
    for name, lo, hi in (("train", None, train_end), ("validation", train_end, val_end),
                         ("test", val_end, None)):
        mask = pd.Series(True, index=frame.index)
        if lo:
            mask &= frame["_anchor"] > lo
        if hi:
            mask &= frame["_anchor"] <= hi
        part = frame[mask]
        # A06 policy: rows observed after the assigned window end are excluded.
        if hi:
            part = part[part["observation_date"] <= hi]
        out[name] = part.drop(columns="_anchor").reset_index(drop=True)
    return out


def load_snapshot(path: Path) -> Tuple[Dict[str, pd.DataFrame], dict]:
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    splits = {name: pd.read_csv(path / f"{name}.csv") for name in ("train", "validation", "test")}
    return splits, manifest


# ------------------------------------------------------------------ preprocessing


class Preprocessor:
    """Training-fitted imputation + feature matrix builder (frozen after ``fit``)."""

    def fit(self, train: pd.DataFrame) -> "Preprocessor":
        area = pd.to_numeric(train["area_sqm"], errors="coerce")
        rooms = pd.to_numeric(train["rooms"], errors="coerce")
        self.global_area = float(area.median()) if area.notna().any() else FALLBACK_AREA_SQM
        self.global_rooms = float(rooms.mode().iloc[0]) if rooms.notna().any() else 2.0
        self.district_area = {str(k): float(v) for k, v in area.groupby(train["district"]).median().dropna().items()}
        self.district_rooms = {
            str(k): float(v.mode().iloc[0])
            for k, v in rooms.groupby(train["district"]) if v.notna().any()
        }
        self.numeric_median = {
            c: float(pd.to_numeric(train[c], errors="coerce").median())
            for c in ("floor", "total_floors", "distance_center_m")
            if pd.to_numeric(train[c], errors="coerce").notna().any()
        }
        self.category_levels = {
            c: sorted(train[c].dropna().astype(str).unique().tolist()) for c in CATEGORICAL_FEATURES
        }
        return self

    def transform(self, frame: pd.DataFrame) -> pd.DataFrame:
        x = pd.DataFrame(index=frame.index)
        district = frame["district"].astype("object")
        for c in NUMERIC_FEATURES:
            x[c] = pd.to_numeric(frame[c], errors="coerce")
        for c in MISSING_INDICATORS:
            x[f"{c}_missing"] = x[c].isna().astype(int)
        x["area_sqm"] = x["area_sqm"].fillna(district.map(self.district_area)).fillna(self.global_area)
        x["rooms"] = x["rooms"].fillna(district.map(self.district_rooms)).fillna(self.global_rooms)
        x["distance_metro_m"] = x["distance_metro_m"].fillna(NO_LANDMARK_M)
        x["distance_university_m"] = x["distance_university_m"].fillna(NO_LANDMARK_M)
        for c, v in self.numeric_median.items():
            x[c] = x[c].fillna(v)
        for c in CATEGORICAL_FEATURES:
            col = frame[c]
            x[c] = col.where(col.notna(), "unknown").astype(str)
        return x

    @property
    def feature_names(self) -> List[str]:
        return NUMERIC_FEATURES + [f"{c}_missing" for c in MISSING_INDICATORS] + CATEGORICAL_FEATURES

    def to_json(self) -> dict:
        return {
            "global_area_sqm": self.global_area, "global_rooms": self.global_rooms,
            "district_median_area_sqm": self.district_area, "district_mode_rooms": self.district_rooms,
            "numeric_median": self.numeric_median, "category_levels": self.category_levels,
            "constants": {"no_landmark_distance_m": NO_LANDMARK_M, "unknown_category": "unknown"},
            "fitted_on": "train split only",
        }


# ------------------------------------------------------------------------ metrics


def metrics(y: np.ndarray, p: np.ndarray) -> dict:
    y, p = np.asarray(y, float), np.asarray(p, float)
    err = p - y
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return {
        "n": int(len(y)),
        "mae": round(float(np.abs(err).mean()), 2),
        "median_ae": round(float(np.median(np.abs(err))), 2),
        "rmse": round(float(np.sqrt((err ** 2).mean())), 2),
        "mape_pct": round(float((np.abs(err) / y).mean() * 100), 2),
        "r2": round(1 - float((err ** 2).sum()) / ss_tot, 4) if ss_tot > 0 else None,
    }


# ---------------------------------------------------------------------- baselines


def run_baseline(train: pd.DataFrame, test: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, dict]:
    """B03 comparable-median baseline, pool = train split only.

    Each test row is queried at its own observation date. The 60-day freshness gate is
    disabled here (``max_freshness_days`` very large) because the pool is, by construction,
    older than every test row; otherwise the baseline would abstain on staleness rather than
    on comparable quality. Abstentions on sparse comparables are kept and reported.
    """
    pool = train.rename(columns={"observation_at": "listing_date"})[
        ["price_usd", "area_sqm", "latitude", "longitude", "district", "listing_date"]
    ]
    model = ComparableMedianBaseline(pool, max_freshness_days=10 ** 6)
    preds = np.full(len(test), np.nan)
    for i, (_, r) in enumerate(test.iterrows()):
        area = r["area_sqm"]
        res = model.predict(
            {"latitude": float(r["latitude"]), "longitude": float(r["longitude"]),
             "district": r["district"] if isinstance(r["district"], str) else None,
             "area_sqm": None if pd.isna(area) else float(area)},
            query_date=str(r["observation_at"]),
        )
        est = res["valuation_assessment"]["estimated_price_usd"]
        if est is not None:
            preds[i] = est
    answered = ~np.isnan(preds)
    return preds, answered, {"abstained": int((~answered).sum()), "answered": int(answered.sum())}


def district_ppsqm_fallback(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    """CONTRACT 'Naive Market Baseline': train-fitted district median price/m2 x area."""
    t = train[pd.to_numeric(train["area_sqm"], errors="coerce") > 0]
    ppsqm = (t["price_usd"] / t["area_sqm"]).groupby(t["district"]).median()
    overall = float((t["price_usd"] / t["area_sqm"]).median())
    area = pd.to_numeric(test["area_sqm"], errors="coerce").fillna(FALLBACK_AREA_SQM)
    return (test["district"].map(ppsqm).fillna(overall) * area).to_numpy()


# --------------------------------------------------------------------- leakage


def leakage_checks(splits: Dict[str, pd.DataFrame], features_used: List[str]) -> dict:
    g = {k: set(v["dedup_group_id"]) for k, v in splits.items()}
    dates = {k: (v["observation_date"].min(), v["observation_date"].max()) for k, v in splits.items() if len(v)}
    overlap = {f"{a}&{b}": len(g[a] & g[b]) for a, b in (("train", "validation"), ("train", "test"), ("validation", "test"))}
    ordered = (dates["train"][1] <= dates["validation"][0] <= dates["validation"][1] <= dates["test"][0]
               if len(splits["validation"]) else dates["train"][1] <= dates["test"][0])
    # Duplicate fingerprints that straddle splits even under different group ids.
    def fp(df):
        keep = df[["latitude", "longitude", "area_sqm", "price_usd"]].dropna()
        return set(zip(keep["latitude"].round(5), keep["longitude"].round(5),
                       keep["area_sqm"].round(1), keep["price_usd"].round(0)))
    prints = {k: fp(v) for k, v in splits.items()}
    near_dup = {f"{a}&{b}": len(prints[a] & prints[b])
                for a, b in (("train", "validation"), ("train", "test"), ("validation", "test"))}
    train = splits["train"]
    forbidden = sorted(set(features_used) & {"price_usd", "original_price", "exchange_rate",
                                             "dedup_group_id", "observation_date", "observation_at"})
    # Target leakage proxy: any single numeric feature explaining the target almost perfectly.
    corr = {}
    for c in NUMERIC_FEATURES:
        s = pd.to_numeric(train[c], errors="coerce")
        ok = s.notna()
        if ok.sum() > 10 and s[ok].std() > 0:
            corr[c] = round(abs(float(np.corrcoef(s[ok], train.loc[ok, "price_usd"])[0, 1])), 3)
    return {
        "group_overlap_between_splits": overlap,
        "chronological_order_ok": bool(ordered),
        "split_date_ranges": {k: list(v) for k, v in dates.items()},
        "near_duplicate_rows_between_splits(coords+area+price)": near_dup,
        "target_derived_columns_in_features": forbidden,
        "max_abs_feature_target_correlation_train": corr,
        "suspicious_if": "any group overlap or near-duplicate > 0, ordering false, forbidden columns present, or |corr| > 0.95",
        "passed": (all(v == 0 for v in overlap.values()) and bool(ordered) and not forbidden
                   and all(v == 0 for v in near_dup.values())
                   and all(v <= 0.95 for v in corr.values())),
    }


class SplitValidationError(RuntimeError):
    """Raised before training when the splits fail the leakage checks."""


def validate_splits(splits: Dict[str, pd.DataFrame], features_used: List[str]) -> dict:
    """Run the leakage checks and refuse to continue if any of them fails."""
    report = leakage_checks(splits, features_used)
    if not report["passed"]:
        raise SplitValidationError(
            "Split validation failed; no model was trained and no artifacts were written.\n"
            + json.dumps(report, indent=2, sort_keys=True, default=str))
    return report


def large_error_review(test: pd.DataFrame, pred: np.ndarray, top: int = 10) -> dict:
    err = pred - test["price_usd"].to_numpy()
    abs_err = np.abs(err)
    order = np.argsort(-abs_err)[:top]
    ppsqm = test["price_usd"] / pd.to_numeric(test["area_sqm"], errors="coerce")
    cols = ["district", "price_usd", "area_sqm", "rooms", "building_type", "observation_date"]
    worst = test.iloc[order][cols].copy()
    worst["predicted_usd"] = np.round(pred[order], 2)
    worst["error_usd"] = np.round(err[order], 2)
    worst["price_per_sqm"] = ppsqm.iloc[order].round(2)
    k = max(1, int(len(test) * 0.05))
    return {
        "worst_rows": json.loads(worst.to_json(orient="records")),
        "share_of_total_abs_error_from_top_5pct_rows": round(float(np.sort(abs_err)[::-1][:k].sum() / abs_err.sum()), 3),
        "rows_with_missing_area_among_top_5pct": int(test.iloc[np.argsort(-abs_err)[:k]]["area_sqm"].isna().sum()),
        "interpretation_hint": "Check whether worst rows are price outliers (extreme price_per_sqm), "
                               "missing-area rows, or sparse districts before treating them as model faults.",
    }


# ------------------------------------------------------------------------- main


def per_district(test: pd.DataFrame, base: np.ndarray, ml: np.ndarray, answered: np.ndarray) -> List[dict]:
    """Both models are compared on the SAME rows (those the baseline answered).

    CatBoost on the full district cohort and the baseline's coverage are reported separately.
    """
    rows = []
    y_all = test["price_usd"].to_numpy()
    for d, idx in test.groupby(test["district"].fillna("unresolved")).indices.items():
        y, a = y_all[idx], answered[idx]
        rows.append({
            "district": d,
            "n_test": int(len(idx)),
            "baseline_coverage": {"answered": int(a.sum()), "abstained": int((~a).sum())},
            "common_rows": {
                "n": int(a.sum()),
                "baseline": metrics(y[a], base[idx][a]) if a.any() else None,
                "catboost": metrics(y[a], ml[idx][a]) if a.any() else None,
            },
            "catboost_full_cohort": metrics(y, ml[idx]),
            "small_sample_warning": int(a.sum()) < 30,
        })
    return sorted(rows, key=lambda r: -r["n_test"])


def run(args: argparse.Namespace) -> dict:
    from catboost import CatBoostRegressor, Pool, __version__ as cb_version

    if args.synthetic:
        splits, manifest = synthetic_snapshot(), {"dataset_version": "SYNTHETIC", "snapshot_sha256": None,
                                                  "contract_version": "n/a"}
    else:
        splits, manifest = load_snapshot(Path(args.snapshot))
    train, val, test = splits["train"], splits["validation"], splits["test"]
    if len(val) == 0:
        raise SystemExit("Validation split is empty (A06 had <3 anchor dates); cannot early-stop honestly.")

    # Validate the splits BEFORE any fitting; a failure stops the experiment.
    leak = validate_splits(splits, Preprocessor().feature_names)

    pre = Preprocessor().fit(train)
    xtr, xva, xte = (pre.transform(d) for d in (train, val, test))
    feats = pre.feature_names
    cat_idx = [feats.index(c) for c in CATEGORICAL_FEATURES]

    model = CatBoostRegressor(**CATBOOST_PARAMS)
    model.fit(Pool(xtr[feats], train["price_usd"], cat_features=cat_idx),
              eval_set=Pool(xva[feats], val["price_usd"], cat_features=cat_idx), use_best_model=True)
    ml_pred = np.maximum(model.predict(Pool(xte[feats], cat_features=cat_idx)), 0.0)
    y = test["price_usd"].to_numpy()

    base_pred, answered, base_cov = run_baseline(train, test)
    naive = district_ppsqm_fallback(train, test)

    common = answered
    result_common = {
        "n": int(common.sum()),
        "baseline_b03_comparable_median": metrics(y[common], base_pred[common]) if common.any() else None,
        "catboost": metrics(y[common], ml_pred[common]) if common.any() else None,
        "naive_district_median_ppsqm": metrics(y[common], naive[common]) if common.any() else None,
    }
    full = {"catboost": metrics(y, ml_pred), "naive_district_median_ppsqm": metrics(y, naive)}

    # Decision rule (fixed before looking at the test numbers): ship ML only when it beats the
    # baseline on MAE AND does not lose on median AE, on the rows both can answer.
    b, m = result_common["baseline_b03_comparable_median"], result_common["catboost"]
    ml_wins = bool(b and m and m["mae"] < b["mae"] and m["median_ae"] <= b["median_ae"])
    decision = "ml" if ml_wins else "baseline"

    importances = sorted(zip(feats, model.get_feature_importance()), key=lambda t: -t[1])

    meta = {
        "experiment_schema_version": EXPERIMENT_SCHEMA_VERSION,
        "model_version": f"{args.version}-catboost",
        "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seed": SEED, "catboost_version": cb_version, "numpy": np.__version__, "pandas": pd.__version__,
        "python": platform.python_version(),
        "catboost_params": CATBOOST_PARAMS, "best_iteration": int(model.get_best_iteration()),
        "dataset": {"version": manifest.get("dataset_version"), "snapshot_sha256": manifest.get("snapshot_sha256"),
                    "contract_version": manifest.get("contract_version"),
                    "split_rows": {k: int(len(v)) for k, v in splits.items()},
                    "is_synthetic": bool(args.synthetic)},
        "serving_decision": decision,
        "fallback": "B03 ComparableMedianBaseline (ml/baseline.py)",
        "decision_rule": "ML only if MAE < baseline MAE and median AE <= baseline median AE on commonly answered test rows",
    }
    report = {
        "metadata": meta,
        "baseline_coverage": {**base_cov, "note": "abstentions = fewer than 3 train comparables within 3 km"},
        "test_common_rows": result_common,
        "test_all_rows": full,
        "neighborhoods": per_district(test, base_pred, ml_pred, answered),
        "validation_mae_catboost": metrics(val["price_usd"].to_numpy(), model.predict(Pool(xva[feats], cat_features=cat_idx)))["mae"],
        "feature_importance": [{"feature": f, "importance": round(float(v), 2)} for f, v in importances],
        "large_errors_catboost": large_error_review(test, ml_pred),
        "large_errors_baseline": large_error_review(test[answered].reset_index(drop=True), base_pred[answered]) if answered.any() else None,
        "leakage": leak,
    }

    out = Path(args.output_dir) / args.version
    out.mkdir(parents=True, exist_ok=True)
    model.save_model(str(out / "model.cbm"))
    (out / "preprocessing.json").write_text(json.dumps(pre.to_json(), indent=2, sort_keys=True), encoding="utf-8")
    (out / "feature_schema.json").write_text(json.dumps({
        "model_features": [{"name": f, "type": "categorical" if f in CATEGORICAL_FEATURES else "numeric"} for f in feats],
        "excluded": EXCLUDED_FEATURES, "target": {"name": "price_usd", "unit": "USD/month"},
        "request_requires": ["latitude", "longitude"], "missing_value_policy": "see preprocessing.json",
    }, indent=2), encoding="utf-8")
    (out / "metadata.json").write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")
    (out / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    digest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir()) if p.name != "SHA256SUMS.json"}
    (out / "SHA256SUMS.json").write_text(json.dumps(digest, indent=2), encoding="utf-8")
    report["artifact_dir"] = str(out)
    return report


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--snapshot", help="A06 snapshot directory (train/validation/test.csv + manifest.json)")
    src.add_argument("--synthetic", action="store_true", help="pipeline smoke test on synthetic data")
    ap.add_argument("--version", required=True)
    ap.add_argument("--output-dir", default="artifacts/b04")
    rep = run(ap.parse_args(argv))
    c = rep["test_common_rows"]
    print(f"decision={rep['metadata']['serving_decision']}  common_rows={c['n']}")
    print("baseline:", c["baseline_b03_comparable_median"])
    print("catboost:", c["catboost"])
    print("leakage passed:", rep["leakage"]["passed"], " artifacts:", rep["artifact_dir"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
