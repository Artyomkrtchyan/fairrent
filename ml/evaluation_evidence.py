"""B08: one reproducible command that produces the evaluation evidence.

    python -m ml.evaluation_evidence --b04 artifacts/b04/<v> --b05 artifacts/b05/<v> \\
        --package artifacts/b07/<v> --snapshot data/processed/<dataset> --output docs/evidence/b08

Writes into ``--output``: ``model_card.md``, ``evaluation_summary.json``, ``risk_rule_validation.json``,
``ontology_evaluation.json``, ``manifest.json`` (input hashes, versions, command) and PNG charts.

Price error (B04/B05 numbers, recomputed predictions) and risk rules (B06) are evaluated in separate sections
on purpose. There are no fraud labels, so nothing here measures fraud accuracy: the rule validation counts how
often *injected* inconsistencies are detected, and the price-anomaly rate is the share of ordinary held-out
listings outside a calibrated interval, not a fraud rate. Deterministic: fixed seed, no timestamps in the data files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from ml import attributions as attr
from ml import calibrate_intervals as ci
from ml import inference as inf
from ml import intervals as iv
from ml import ontology_rules as rules
from ml import train_compare as tc
from ml import validate_proximity as vp

EVIDENCE_VERSION = "b08-v1"
SEED = 20261104
ONTOLOGY_SAMPLE_ROWS = 300
SHAP_SAMPLE_ROWS = 20
MIN_DISTRICT_ROWS = 50
PRICE_MULTIPLIERS = (0.5, 0.7, 0.85, 1.0, 1.15, 1.3, 1.5, 2.0, 3.0)
_NAMESPACE = uuid.UUID("5d0f3f5e-8b0a-4e7e-9a55-7c1c0b8d4a21")

# Entity colours are fixed across charts (reference palette slots 1-3; first three validate for all pairs).
COLORS = {"CatBoost (B04)": "#2a78d6", "B03 baseline": "#eb6834", "Naive district median": "#1baf7a"}
INK, INK_2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e3e2de", "#fcfcfb"


# ----------------------------------------------------------------------------- helpers


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def wilson(k: int, n: int, z: float = 1.96) -> Tuple[Optional[float], Optional[float]]:
    """95% Wilson score interval for a proportion."""
    if n == 0:
        return None, None
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)


def _rate(k: int, n: int) -> Dict[str, Any]:
    low, high = wilson(k, n)
    return {"detected": int(k), "n": int(n), "rate": round(k / n, 4) if n else None, "ci95_low": low, "ci95_high": high}


def _num(value: Any) -> Optional[float]:
    return rules._num(value)


def _row_listing(row: Mapping[str, Any]) -> Dict[str, Any]:
    return {"latitude": row.get("latitude"), "longitude": row.get("longitude"), "district": row.get("district"),
            "area_sqm": row.get("area_sqm"), "rooms": row.get("rooms"), "floor": row.get("floor"),
            "total_floors": row.get("total_floors"), "coordinate_confidence": row.get("coordinate_confidence")}


def _statuses(result: Mapping[str, Any]) -> Dict[str, str]:
    return {c["rule_id"]: c["status"] for c in result["checks"]} | {f["rule_id"]: f["status"] for f in result["facts"]}


# ----------------------------------------------------------------------------- inputs


def load_inputs(b04: Path, b05: Path, package_dir: Path, snapshot: Path) -> Dict[str, Any]:
    meta04, _, _, model_sha = ci.load_b04(b04)                      # verifies B04 checksums
    report04 = _read_json(b04 / "report.json")
    report05 = _read_json(b05 / "b05_report.json")
    for name, digest in _read_json(b05 / "SHA256SUMS.json").items():
        if _sha256(b05 / name) != digest:
            raise ci.ArtifactError(f"B05 artifact {name} does not match SHA256SUMS.json")
    package = inf.load_package(package_dir)                         # verifies package checksums
    ci.verify_snapshot_digest(snapshot)
    splits, manifest = tc.load_snapshot(snapshot)
    if not (meta04["dataset"]["snapshot_sha256"] == report05["metadata"]["snapshot_sha256"]
            == package.manifest["snapshot_sha256"] == manifest["snapshot_sha256"]):
        raise ci.ArtifactError("B04, B05, the package and the snapshot do not refer to the same snapshot")
    if report05["metadata"]["b04_model_sha256"] != model_sha or package.manifest["model_sha256"] != model_sha:
        raise ci.ArtifactError("B05 or the package was built for a different B04 model")
    # The interval metrics (B05 report) and the risk results (computed with the packaged calibration) must describe the
    # same calibration: compare the calibration file byte for byte, then the identifying fields.
    packaged_sha = _read_json(package_dir / "SHA256SUMS.json").get("interval_calibration.json")
    if _sha256(b05 / "interval_calibration.json") != packaged_sha:
        raise ci.ArtifactError("the B05 calibration does not match the calibration packaged in B07 "
                               "(interval_calibration.json differs); rebuild the package from this B05 artifact")
    meta05 = report05["metadata"]
    if (meta05.get("method") != package.calibration.method
            or package.manifest["calibration_version"] != package.calibration.calibration_version):
        raise ci.ArtifactError("B05 report and packaged calibration disagree on the calibration method or version")
    return {"meta04": meta04, "report04": report04, "report05": report05, "package": package,
            "splits": splits, "manifest": manifest, "model_sha": model_sha, "dirs": (b04, b05, package_dir, snapshot)}


# ------------------------------------------------------------------------ price section


def price_section(inputs: Mapping[str, Any]) -> Dict[str, Any]:
    r4, r5 = inputs["report04"], inputs["report05"]
    common = r4["test_common_rows"]
    held = r5["held_out_test"]
    levels = {lv: {"nominal": float(lv), "coverage": v["served_rows"]["coverage"],
                   "median_width_usd": v["served_rows"]["median_width_usd"],
                   "median_width_ratio": v["served_rows"]["median_width_ratio"], "n_served": v["served_rows"]["n"]}
              for lv, v in held.items()}
    return {
        "source": "B04 report.json and B05 b05_report.json (not recomputed)",
        "decision": inputs["meta04"]["serving_decision"], "decision_rule": inputs["meta04"]["decision_rule"],
        "test_common_rows": common, "test_all_rows": r4["test_all_rows"],
        "baseline_coverage": r4["baseline_coverage"],
        "neighborhoods": [{"district": n["district"], "n_test": n["n_test"], "baseline": n["common_rows"]["baseline"],
                           "catboost": n["common_rows"]["catboost"], "small_sample_warning": n["small_sample_warning"]}
                          for n in r4["neighborhoods"]],
        "feature_importance": r4["feature_importance"], "intervals": levels,
        "targets": r5["targets_vs_results"], "abstention": r5["abstention"],
        "conditional_coverage_by_area_bin": r5["conditional_coverage"].get("by_area_bin"),
        "leakage_passed": r4["leakage"]["passed"], "temporal_split": inputs["meta04"]["dataset"]["temporal_split"],
        "evidence_level": inputs["meta04"]["evidence_level"], "split_rows": inputs["meta04"]["dataset"]["split_rows"],
        "b04_limitations": r4.get("limitations", []), "b05_limitations": r5.get("limitations", []),
    }


def predictions(inputs: Mapping[str, Any]) -> pd.DataFrame:
    """Held-out predictions with the serving decision and the price-anomaly status of the actual asking price."""
    package, test = inputs["package"], inputs["splits"]["test"].reset_index(drop=True)
    pred = tc.predict_usd(package.model, package.preprocessor, test)
    gate = package.gate.reasons(test)
    out = test.copy()
    out["pred_usd"] = pred
    lows, highs, status = [], [], []
    for i, p in enumerate(pred):
        reasons = gate[i] + iv.prediction_reasons(p)[0]
        interval = iv.prediction_interval(float(p), package.calibration, reasons=reasons)
        lows.append(interval["lower_bound_usd"]); highs.append(interval["upper_bound_usd"])
        status.append(iv.price_status(float(test["price_usd"].iloc[i]), interval))
    out["lower_usd"], out["upper_usd"], out["price_status"] = lows, highs, status
    out["served"] = [not g for g in gate]
    return out


def interval_for_row(lower: Any, upper: Any, package: Any) -> Optional[Dict[str, Any]]:
    """The calibrated interval of a prediction row, or None when it was withheld.

    Withheld bounds are None in Python but become NaN once stored in a DataFrame column, so both must count as
    "no interval"; otherwise withheld rows leak into every rate that is computed over served rows."""
    if lower is None or upper is None or not (math.isfinite(float(lower)) and math.isfinite(float(upper))):
        return None
    return {"lower_bound_usd": float(lower), "upper_bound_usd": float(upper),
            "confidence_level": package.calibration.primary_level,
            "calibration_version": package.calibration.calibration_version}


def price_anomaly_section(pred: pd.DataFrame) -> Dict[str, Any]:
    served = pred[pred["price_status"] != "insufficient_data"]
    counts = {k: int((served["price_status"] == k).sum()) for k in ("within_range", "above_range", "below_range")}
    n = len(served)
    return {"served_rows": n, "withheld_rows": int(len(pred) - n), "counts": counts,
            "outside_rate": round((counts["above_range"] + counts["below_range"]) / n, 4) if n else None,
            "interpretation": ("Share of ordinary held-out listings whose asking price falls outside the calibrated "
                               "interval. It is about 1 - coverage by construction and is NOT a fraud rate.")}


# ------------------------------------------------------------------- risk rule validation


def _eval_rows(rows: Sequence[Mapping[str, Any]], support: rules.DistrictSupport,
               intervals: Optional[Sequence[Optional[Mapping[str, Any]]]] = None,
               titles: Optional[Sequence[Optional[str]]] = None, prices: Optional[Sequence[Any]] = None
               ) -> List[Dict[str, str]]:
    out = []
    for i, row in enumerate(rows):
        listing = _row_listing(row)
        if titles is not None:
            listing["title"] = titles[i]
        if prices is not None:
            listing["asking_price_usd"] = prices[i]
        interval = intervals[i] if intervals is not None else None
        out.append(_statuses(rules.evaluate_listing(listing, district_support=support, interval=interval)))
    return out


def _title(row: Mapping[str, Any], *, rooms: Optional[int] = None, area: Optional[float] = None,
           district: Optional[str] = None, floor: Optional[int] = None) -> str:
    geo = rules._geography()
    district_id = rules._district_id(district or row["district"])
    label = geo.DISTRICTS[district_id][0]
    rooms = int(row["rooms"]) if rooms is None else rooms
    area = float(row["area_sqm"]) if area is None else area
    floor = int(row["floor"]) if floor is None else floor
    return f"{rooms} room apartment, {label}, {floor}/{int(row['total_floors'])} floor, {area:g} m2"


def risk_validation(inputs: Mapping[str, Any], pred: pd.DataFrame) -> Dict[str, Any]:
    package = inputs["package"]
    support, geo = package.district_support, rules._geography()
    test = pred.reset_index(drop=True)
    rng = np.random.default_rng(SEED)
    rows = test.to_dict("records")
    intervals = [interval_for_row(lo, hi, package) for lo, hi in zip(test["lower_usd"], test["upper_usd"])]

    # A. flag rates on unmodified rows -------------------------------------------------------
    base = _eval_rows(rows, support, intervals, prices=list(test["price_usd"]))
    rates: Dict[str, Dict[str, int]] = {}
    for statuses in base:
        for rule_id, status in statuses.items():
            rates.setdefault(rule_id, {}).setdefault(status, 0)
            rates[rule_id][status] += 1
    flag_rates = {rid: {"n": sum(v.values()), **dict(sorted(v.items()))} for rid, v in sorted(rates.items())}

    # B. injected defects ----------------------------------------------------------------------
    experiments: Dict[str, Any] = {}

    eligible = [i for i, s in enumerate(base) if s.get("GEO-DISTRICT-SUPPORT") == "clear"]
    swapped_rows, kept = [], []
    for i in eligible:
        row = dict(rows[i])
        counts = support.block_counts(float(row["latitude"]), float(row["longitude"]))
        options = sorted(d for d in geo.DISTRICTS if counts.get(d, 0) == 0)
        if options:
            row["district"] = geo.DISTRICTS[options[int(rng.integers(len(options)))]][0]
            swapped_rows.append(row); kept.append(i)
    res = _eval_rows(swapped_rows, support)
    experiments["district_label_swapped_to_unsupported_district"] = {
        "rule": "GEO-DISTRICT-SUPPORT", **_rate(sum(r["GEO-DISTRICT-SUPPORT"] == "flagged" for r in res), len(res)),
        "population": "rows whose district check was determinable and clear",
        "note": "Detects a label that never occurs near the pin; cannot say whether the label or the pin is wrong."}

    area_rows = [i for i, r in enumerate(rows) if _num(r.get("area_sqm")) and r["area_sqm"] > 0]
    for factor in (10, 3, 2):
        mod = [{**rows[i], "area_sqm": float(rows[i]["area_sqm"]) * factor} for i in area_rows]
        res = _eval_rows(mod, support)
        experiments[f"area_multiplied_by_{factor}"] = {
            "rule": "FEAT-AREA-PLAUSIBILITY",
            **_rate(sum(r["FEAT-AREA-PLAUSIBILITY"] == "flagged" for r in res), len(res)),
            "population": "rows with a known area",
            "note": ("Fixed plausibility bounds catch large typing errors only; moderate errors are expected to pass."
                     if factor < 10 else "A tenfold typing error (for example a thousands separator).")}

    text_rows = [i for i, r in enumerate(rows) if all(_num(r.get(k)) is not None for k in
                 ("area_sqm", "rooms", "floor", "total_floors")) and rules._district_id(r.get("district"))
                 and r["area_sqm"] > 0 and r["rooms"] >= 1]
    desc_rules = ("DESC-AREA-MATCH", "DESC-ROOMS-MATCH", "DESC-FLOOR-MATCH", "DESC-DISTRICT-MATCH")
    clean = _eval_rows([rows[i] for i in text_rows], support, titles=[_title(rows[i]) for i in text_rows])
    experiments["consistent_synthetic_text_false_flags"] = {
        "rule": "DESC-*", "n": len(clean),
        "false_flags_by_rule": {rid: sum(r[rid] == "flagged" for r in clean) for rid in desc_rules},
        "clear_by_rule": {rid: sum(r[rid] == "clear" for r in clean) for rid in desc_rules},
        "note": "Text built from the same fields; every flag here would be a false positive."}
    corruptions = {
        "text_rooms_differs": ("DESC-ROOMS-MATCH", lambda r, g: {"rooms": int(r["rooms"]) + 1}),
        "text_area_differs_by_50pct": ("DESC-AREA-MATCH", lambda r, g: {"area": float(r["area_sqm"]) * 1.5}),
        "text_floor_differs": ("DESC-FLOOR-MATCH",
                               lambda r, g: {"floor": int(r["floor"]) - 1 if r["floor"] >= 1 and r["floor"] == r["total_floors"]
                                             else int(r["floor"]) + 1}),
        "text_district_differs": ("DESC-DISTRICT-MATCH", lambda r, g: {"district": next(
            geo.DISTRICTS[d][0] for d in sorted(geo.DISTRICTS) if d != rules._district_id(r["district"]))}),
    }
    for name, (rule_id, make) in corruptions.items():
        titles = [_title(rows[i], **make(rows[i], geo)) for i in text_rows]
        res = _eval_rows([rows[i] for i in text_rows], support, titles=titles)
        experiments[name] = {"rule": rule_id, **_rate(sum(r[rule_id] == "flagged" for r in res), len(res)),
                             "population": "rows with area, rooms, floors and a resolvable district",
                             "note": "Synthetic text built from the fields, then changed in one element; "
                                     "tests the rule and parser, not real descriptions (the export has none)."}

    no_coords = [{**r, "latitude": None, "longitude": None} for r in rows]
    res = _eval_rows(no_coords, support)
    facts = ("GEO-PROX-METRO", "GEO-PROX-UNIVERSITY", "GEO-PROX-CENTER")
    experiments["coordinates_removed"] = {
        "rule": "GEO-*", "n": len(res),
        "facts_unknown": _rate(sum(all(r[f] == "unknown" for f in facts) for r in res), len(res)),
        "geo_flags": sum(r["GEO-DISTRICT-SUPPORT"] == "flagged" for r in res),
        "note": "Missing data must give 'unknown', never an invented fact or a flag."}

    served = [i for i, iv_ in enumerate(intervals) if iv_ is not None]
    sensitivity = []
    for factor in PRICE_MULTIPLIERS:
        flagged = sum(iv.price_status(float(rows[i]["price_usd"]) * factor, intervals[i]) in ("above_range", "below_range")
                      for i in served)
        sensitivity.append({"price_multiplier": factor, **_rate(flagged, len(served))})
    return {"seed": SEED, "evaluated_rows": len(rows), "no_fraud_labels": True,
            "flag_rates_on_unmodified_rows": flag_rates, "injected_defects": experiments,
            "price_anomaly_sensitivity": {"population": "served held-out rows; asking price = actual x multiplier",
                                          "points": sensitivity,
                                          "note": "Multiplier 1.0 is the natural outside-interval rate. A wide 95% "
                                                  "interval only flags large deviations."},
            "interpretation": ("Detection rates are for injected, synthetic inconsistencies. They say nothing about how "
                               "many real listings are fraudulent or how many fraudulent listings the rules would catch.")}


# ------------------------------------------------------------------- ontology evaluation


def ontology_evaluation(inputs: Mapping[str, Any], pred: pd.DataFrame) -> Dict[str, Any]:
    try:
        from ml import ontology_graph as og
        from ontology import demo_inference as demo
    except ImportError as error:
        return {"available": False, "reason": f"rdflib not installed ({error})"}
    package = inputs["package"]
    sample = pred.reset_index(drop=True).iloc[:ONTOLOGY_SAMPLE_ROWS]
    items = []
    for index, row in sample.iterrows():
        listing = _row_listing(row)
        listing["asking_price_usd"] = row["price_usd"]
        interval = interval_for_row(row["lower_usd"], row["upper_usd"], package)
        result = rules.evaluate_listing(listing, district_support=package.district_support, interval=interval)
        learned = None
        if index < SHAP_SAMPLE_ROWS:
            frame = pd.DataFrame([{k: row.get(k) for k in tc.NUMERIC_FEATURES + tc.CATEGORICAL_FEATURES}])
            x = package.preprocessor.transform(frame)[package.preprocessor.feature_names]
            learned = attr.explain_with_catboost(package.model, x, cat_features=tc.CATEGORICAL_FEATURES)
        items.append({"listing_id": str(uuid.uuid5(_NAMESPACE, f"test-{index}")), "result": result, "learned": learned})
    graph = og.build_graph(items)
    questions = {}
    for key, (text, _) in og.CQ.items():
        answers = og.answer(graph, key)
        questions[key] = {"question": text, "answer_count": len(answers),
                          "distinct_listings": len({a["listing"] for a in answers}), "first_answers": answers[:3]}
    golden = [demo.summarise(e, demo.run_example(e)) for e in demo.EXAMPLES]
    return {"available": True, "ontology_triples": len(og.load_ontology()), "graph_triples": len(graph),
            "listings_in_graph": len(items), "learned_effect_listings": SHAP_SAMPLE_ROWS,
            "competency_questions": questions, "inferred_facts_disjoint_from_learned_effects": og.separation_holds(graph),
            "worked_examples": golden,
            "note": ("The graph is a queryable view of rule output for a sample of held-out listings; the competency "
                     "questions test that the ontology can answer them, not that the answers are correct about reality.")}


# ----------------------------------------------------------------------------- charts


def _style(ax: Any, title: str) -> None:
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", fontsize=11, color=INK, fontweight="bold")
    ax.grid(axis="y", color=GRID, linewidth=0.8); ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=9, length=0)


def _save(fig: Any, path: Path, bottom: Optional[float] = None) -> None:
    fig.patch.set_facecolor(SURFACE)
    fig.tight_layout(rect=(0, bottom or 0, 1, 1))
    fig.savefig(path, dpi=140, facecolor=SURFACE, metadata={"Software": "matplotlib"})


def make_charts(summary: Mapping[str, Any], pred: pd.DataFrame, out: Path) -> List[str]:
    import matplotlib
    import matplotlib.ticker
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    names = {"catboost": "CatBoost (B04)", "baseline_b03_comparable_median": "B03 baseline",
             "naive_district_median_ppsqm": "Naive district median"}
    price, files = summary["price_error"], []

    # 1. headline comparison (same rows for all three models) --------------------------------
    common = price["test_common_rows"]
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.8))
    for ax, metric, title in zip(axes, ("mae", "median_ae"), ("Mean absolute error (USD/month)", "Median absolute error (USD/month)")):
        _style(ax, title)
        for i, key in enumerate(names):
            value = common[key][metric]
            ax.bar(i, value, color=COLORS[names[key]], width=0.62, label=names[key])
            ax.text(i, value, f"{value:,.0f}", ha="center", va="bottom", fontsize=9, color=INK)
        ax.set_xticks([])
        ax.set_ylim(0, max(common[k][metric] for k in names) * 1.18)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, fontsize=9, loc="lower center", ncol=3)
    fig.suptitle(f"Held-out test, {common['n']:,} listings answerable by all three (lower is better)", x=0.01, ha="left",
                 fontsize=9, color=INK_2)
    _save(fig, out / "price_model_comparison.png", bottom=0.12); plt.close(fig); files.append("price_model_comparison.png")

    # 2. per district -------------------------------------------------------------------------
    hoods = [n for n in price["neighborhoods"] if n["n_test"] >= MIN_DISTRICT_ROWS]
    hoods.sort(key=lambda n: -n["n_test"])
    fig, ax = plt.subplots(figsize=(max(6.5, 1.1 * len(hoods) + 2), 3.9))
    _style(ax, "Mean absolute error by district (USD/month)")
    width = 0.38
    for j, (key, label) in enumerate((("baseline", "B03 baseline"), ("catboost", "CatBoost (B04)"))):
        xs = np.arange(len(hoods)) + (j - 0.5) * width
        vals = [n[key]["mae"] for n in hoods]
        ax.bar(xs, vals, width=width * 0.92, color=COLORS[label], label=label)
        for x, v in zip(xs, vals):
            ax.text(x, v, f"{v:,.0f}", ha="center", va="bottom", fontsize=8, color=INK)
    ax.set_xticks(np.arange(len(hoods)))
    ax.set_xticklabels([f"{'no district' if n['district'] == 'unresolved' else n['district']}\n(n={n['n_test']})"
                        for n in hoods], fontsize=8)
    ax.legend(frameon=False, fontsize=8)
    fig.text(0.01, 0.01, f"Districts with at least {MIN_DISTRICT_ROWS} test listings; smaller ones are in the JSON.",
             fontsize=8, color=INK_2)
    _save(fig, out / "price_error_by_district.png", bottom=0.05); plt.close(fig); files.append("price_error_by_district.png")

    # 3. interval calibration -------------------------------------------------------------------
    levels = sorted(price["intervals"].values(), key=lambda v: v["nominal"])
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.8))
    ax = axes[0]; _style(ax, "Observed vs nominal coverage")
    nominal = [v["nominal"] for v in levels]
    ax.plot([0.75, 1.0], [0.75, 1.0], color=INK_2, linewidth=1, linestyle="--", label="ideal")
    ax.plot(nominal, [v["coverage"] for v in levels], color=COLORS["CatBoost (B04)"], linewidth=2, marker="o",
            markersize=8, label="held-out test")
    for v in levels:
        ax.text(v["nominal"] - 0.004, v["coverage"] + 0.012, f"{v['coverage']:.1%}", ha="right", va="bottom", fontsize=8, color=INK)
    ax.set_xlabel("nominal level", fontsize=9, color=INK_2); ax.set_ylabel("observed coverage", fontsize=9, color=INK_2)
    ax.set_xticks(nominal); ax.set_xlim(0.77, 0.98); ax.set_ylim(0.75, 1.0); ax.legend(frameon=False, fontsize=8, loc="upper left")
    ax = axes[1]; _style(ax, "Median interval width / predicted price")
    for i, v in enumerate(levels):
        ax.bar(i, v["median_width_ratio"], color=COLORS["CatBoost (B04)"], width=0.55,
               label="CatBoost + conformal" if i == 0 else None)
        ax.text(i, v["median_width_ratio"], f"{v['median_width_ratio']:.2f}\n(${v['median_width_usd']:,.0f})",
                ha="center", va="bottom", fontsize=8, color=INK)
    target = price["targets"]["width_ratio_target"]["value"]
    ax.axhline(target, color=COLORS["B03 baseline"], linewidth=1.5, linestyle="--", label=f"provisional target {target}")
    ax.set_xticks(range(len(levels))); ax.set_xticklabels([f"{v['nominal']:.0%}" for v in levels], fontsize=9)
    ax.set_ylim(0, max(v["median_width_ratio"] for v in levels) * 1.3); ax.legend(frameon=False, fontsize=8, loc="upper left")
    _save(fig, out / "interval_calibration.png"); plt.close(fig); files.append("interval_calibration.png")

    # 4. predicted vs actual --------------------------------------------------------------------
    served = pred[pred["price_status"] != "insufficient_data"]
    fig, ax = plt.subplots(figsize=(5.4, 5.0)); _style(ax, "Held-out: predicted vs asking price (USD/month)")
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.scatter(served["price_usd"], served["pred_usd"], s=9, alpha=0.35, color=COLORS["CatBoost (B04)"], linewidths=0)
    lim = [max(50, float(min(served["price_usd"].min(), served["pred_usd"].min()))),
           float(max(served["price_usd"].max(), served["pred_usd"].max())) * 1.1]
    ax.plot(lim, lim, color=INK_2, linewidth=1, linestyle="--")
    ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlim(lim); ax.set_ylim(lim)
    ax.set_xlabel("asking price", fontsize=9, color=INK_2); ax.set_ylabel("model prediction", fontsize=9, color=INK_2)
    _save(fig, out / "predicted_vs_actual.png"); plt.close(fig); files.append("predicted_vs_actual.png")

    # 5. rule validation (risk, separate from price error) -------------------------------------
    risk = summary["risk_rules"]["injected_defects"]
    keys = [k for k, v in risk.items() if "rate" in v and v["rate"] is not None]
    fig, ax = plt.subplots(figsize=(8.2, 0.55 * len(keys) + 1.6)); _style(ax, "Detection of injected inconsistencies (not fraud)")
    ax.grid(axis="y", visible=False); ax.grid(axis="x", color=GRID, linewidth=0.8)
    for i, k in enumerate(keys):
        v = risk[k]
        ax.barh(i, v["rate"], color=COLORS["CatBoost (B04)"], height=0.6)
        ax.text(v["rate"] + 0.02, i, f"{v['rate']:.0%}  (n={v['n']:,})", va="center", fontsize=8, color=INK)
    ax.set_yticks(range(len(keys))); ax.set_yticklabels([k.replace("_", " ") for k in keys], fontsize=8)
    ax.invert_yaxis(); ax.set_xlim(0, 1.25); ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_xticklabels(["0%", "25%", "50%", "75%", "100%"])
    fig.text(0.01, 0.01, "Synthetic defects: 100% shows a rule fires as designed, not recall on real errors.",
             fontsize=8, color=INK_2)
    _save(fig, out / "rule_validation.png", bottom=0.05); plt.close(fig); files.append("rule_validation.png")

    # 6. price anomaly sensitivity ---------------------------------------------------------------
    pts = summary["risk_rules"]["price_anomaly_sensitivity"]["points"]
    fig, ax = plt.subplots(figsize=(6.2, 3.8)); _style(ax, "Price-anomaly flag rate vs asking-price multiplier")
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    xs = [p["price_multiplier"] for p in pts]; ys = [p["rate"] for p in pts]
    ax.plot(xs, ys, color=COLORS["CatBoost (B04)"], linewidth=2, marker="o", markersize=8)
    for x, y in zip(xs, ys):
        ax.text(x, y + 0.04, f"{y:.0%}", ha="center", fontsize=8, color=INK)
    ax.set_xscale("log"); ax.set_xticks(xs); ax.set_xticklabels([f"x{m:g}" for m in xs], fontsize=8)
    ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    ax.set_ylim(0, 1.12); ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0]); ax.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
    ax.set_xlabel("actual asking price x multiplier (x1 = unmodified)", fontsize=9, color=INK_2)
    _save(fig, out / "price_anomaly_sensitivity.png"); plt.close(fig); files.append("price_anomaly_sensitivity.png")
    return files


# --------------------------------------------------------------------------- model card


def _row(label: str, m: Mapping[str, Any]) -> str:
    return f"| {label} | {m['mae']:,.2f} | {m['median_ae']:,.2f} | {m['mape_pct']:.2f} | {m['rmse']:,.2f} | {m['r2']:.3f} |"


def model_card(summary: Mapping[str, Any], manifest: Mapping[str, Any]) -> str:
    p, risk, onto = summary["price_error"], summary["risk_rules"], summary["ontology"]
    v, common = manifest["versions"], p["test_common_rows"]
    cat, base = common["catboost"], common["baseline_b03_comparable_median"]
    imp = ", ".join(f"{f['feature']} ({f['importance']:.1f})" for f in p["feature_importance"][:5])
    lv = p["intervals"]
    primary = lv[max(lv, key=float)]
    tgt = p["targets"]
    lines = [
        "# Model card: Fairrent rental price estimate and rule engine", "",
        f"Generated by `ml.evaluation_evidence` (evidence version `{EVIDENCE_VERSION}`). Every number below comes from "
        "the B04/B05 reports or from the commands in section 9; nothing is typed in by hand.", "",
        "## 1. Summary", "",
        f"- Estimates the **monthly asking rent in USD** of a Yerevan apartment from its coordinates and, optionally, "
        f"area, rooms, floors, district and building type. The estimate comes with a conformal prediction interval.",
        f"- On {common['n']:,} held-out listings the CatBoost model has a mean absolute error of **${cat['mae']:,.2f}** "
        f"versus **${base['mae']:,.2f}** for the B03 comparable-median baseline "
        f"({1 - cat['mae'] / base['mae']:.0%} lower), and a median absolute error of ${cat['median_ae']:,.2f} "
        f"versus ${base['median_ae']:,.2f}.",
        f"- The nominal 95% interval covered **{primary['coverage']:.1%}** of held-out asking prices, but it is wide: "
        f"median width ${primary['median_width_usd']:,.0f} (**{primary['median_width_ratio']:.2f}** of the predicted price; "
        f"provisional target {tgt['width_ratio_target']['value']} is "
        f"{'met' if tgt['width_ratio_target']['met'] else 'NOT met'}).",
        "- Risk rules (section 6) are evaluated separately. **Fraud accuracy was not measured**: no labelled fraud "
        "data exists.", "",
        "## 2. Intended use and out of scope", "",
        "**Intended:** decision support for a municipal reviewer or a renter comparing an asking price with a calibrated "
        "range for similar listings; surfacing listings whose data is inconsistent so a person can look at them.", "",
        "**Not intended / not supported:**",
        "- Deciding that a listing is fraudulent. A price outside the interval and a rule finding are *review evidence* only.",
        "- Signed rents, sale prices, or any city other than Yerevan (coordinates outside the coverage box are rejected).",
        "- Forecasting future prices. The evaluation is in-time (see limitations).",
        "- Automated action against a landlord or advertiser.", "",
        "## 3. Versions and data", "",
        f"| Item | Value |", "|---|---|",
        f"| Package | `{v['package_version']}` (interface `{v['interface_version']}`) |",
        f"| Model | `{v['model_version']}` (CatBoost, MAE loss) |",
        f"| Calibration | `{v['calibration_version']}`, method `{manifest['calibration']['method']}`, primary level {manifest['calibration']['primary_level']} |",
        f"| Rules | `{v['rules_version']}`, geography `{v['geography_version']}`, ontology v1.1 |",
        f"| Dataset | `{v['dataset_version']}`, snapshot SHA-256 `{manifest['inputs']['snapshot_sha256'][:16]}...` |",
        f"| Rows (train / validation / test) | {p['split_rows']['train']:,} / {p['split_rows']['validation']:,} / {p['split_rows']['test']:,} |",
        f"| Data as of | {v['data_as_of']} |",
        f"| Split | {'chronological' if p['temporal_split'] else 'grouped-random (one-date scrape), duplicate groups isolated'} |",
        f"| Leakage checks | {'passed' if p['leakage_passed'] else 'FAILED'} |", "",
        "Source: asking-price listings scraped from list.am, converted to USD per month by the A06 pipeline. Targets are "
        "asking prices, not signed rents.", "",
        "## 4. Price error (held-out test)", "",
        f"Same {common['n']:,} rows for every model (rows the baseline can answer; baseline abstained on "
        f"{p['baseline_coverage']['abstained']}). Lower is better except R-squared.", "",
        "| Model | MAE (USD) | Median AE (USD) | MAPE (%) | RMSE (USD) | R-squared |", "|---|---|---|---|---|---|",
        _row("CatBoost (B04)", cat), _row("B03 baseline", base),
        _row("Naive district median", common["naive_district_median_ppsqm"]), "",
        f"Serving decision rule: *{p['decision_rule']}*. Decision: **{p['decision']}**. "
        f"Largest model inputs by importance: {imp}.", "",
        "![Model comparison](price_model_comparison.png)", "", "![By district](price_error_by_district.png)", "",
        "![Predicted vs actual](predicted_vs_actual.png)", "",
        "### Prediction intervals", "",
        "| Nominal | Observed coverage | Median width (USD) | Median width / price |", "|---|---|---|---|",
        *[f"| {x['nominal']:.0%} | {x['coverage']:.1%} | {x['median_width_usd']:,.0f} | {x['median_width_ratio']:.2f} |"
          for x in sorted(lv.values(), key=lambda x: x["nominal"])], "",
        f"Coverage target {tgt['coverage_target']['value']:.0%}: {'met' if tgt['coverage_target']['met'] else 'NOT met'}. "
        f"Width target {tgt['width_ratio_target']['value']}: {'met' if tgt['width_ratio_target']['met'] else 'NOT met'}. "
        f"Intervals are withheld for {p['abstention']['share']:.1%} of rows "
        f"({', '.join(f'{k}: {n}' for k, n in p['abstention']['reason_counts'].items() if k != 'rows_withheld')}).", "",
        "![Interval calibration](interval_calibration.png)", "",
        "## 5. Ontology and competency questions", "",
    ]
    if onto.get("available"):
        lines += [f"Ontology v1.1: {onto['ontology_triples']} schema/sample triples; the evaluation graph adds rule output "
                  f"for {onto['listings_in_graph']} held-out listings ({onto['graph_triples']:,} triples in total). "
                  f"Inferred facts and learned price effects are disjoint: **{onto['inferred_facts_disjoint_from_learned_effects']}**.", "",
                  "| Competency question | Answers | Listings |", "|---|---|---|",
                  *[f"| {k}: {q['question']} | {q['answer_count']} | {q['distinct_listings']} |"
                    for k, q in onto["competency_questions"].items()], "",
                  *(["CQ4 has no answers here because every sampled listing has coordinates; the missing-data case is "
                     "demonstrated by the worked examples.", ""]
                    if onto["competency_questions"]["CQ4"]["answer_count"] == 0 else []),
                  "Three worked examples (typical, inconsistent, missing data) are in `ontology_evaluation.json` and "
                  "`ontology/examples/b06_inference_examples.json`.", ""]
    else:
        lines += [f"Not generated: {onto.get('reason')}.", ""]
    prox = summary["proximity_price_effect"]
    lines += ["### Proximity: inferred fact versus price effect", ""]
    if prox.get("available") and prox.get("near_vs_far_overall"):
        o = prox["near_vs_far_overall"]
        lines += [f"Near-metro listings (within {prox['near_m']:.0f} m) have a median price per m2 {o['ratio']:.2f}x that of "
                  f"far ones (beyond {prox['far_m']:.0f} m; 95% bootstrap CI {o['ci95_low']:.2f}-{o['ci95_high']:.2f}). "
                  "Inside districts the ratio is "
                  + ("; ".join(f"{w['district']} {w['ratio']:.2f} ({w['ci95_low']:.2f}-{w['ci95_high']:.2f})"
                               for w in prox["near_vs_far_within_district"]) or "not estimable (too few listings)")
                  + ". The gap shrinks inside districts, so much of it is location mix. Descriptive, not causal.", ""]
    lines += [
        "## 6. Risk rules (evaluated separately from price error)", "",
        "No fraud labels exist. The numbers below therefore measure rule behaviour, not fraud detection.", "",
        f"**Price anomaly.** {summary['price_anomaly']['outside_rate']:.1%} of ordinary held-out listings have an asking "
        "price outside the calibrated interval, as expected from 95% intervals; it is not a fraud rate. "
        "Flagging needs a large deviation because the interval is wide:", "",
        "| Asking price vs actual | " + " | ".join(f"x{x['price_multiplier']:g}" for x in risk["price_anomaly_sensitivity"]["points"]) + " |",
        "|---|" + "---|" * len(risk["price_anomaly_sensitivity"]["points"]),
        "| Flagged | " + " | ".join(f"{x['rate']:.0%}" for x in risk["price_anomaly_sensitivity"]["points"]) + " |", "",
        "![Price anomaly sensitivity](price_anomaly_sensitivity.png)", "",
        "**Consistency rules on unmodified held-out listings** (flagged / clear / unknown):", "",
        "| Rule | Flagged | Clear | Unknown |", "|---|---|---|---|",
        *[f"| {rid} | {c.get('flagged', 0)} | {c.get('clear', 0)} | {c.get('unknown', 0)} |"
          for rid, c in risk["flag_rates_on_unmodified_rows"].items() if rid.startswith(("GEO-DISTRICT", "DESC", "FEAT"))], "",
        *(["Description rules are `unknown` on this data because the export carries no free text.", ""]
          if all(risk["flag_rates_on_unmodified_rows"].get(r, {}).get("unknown") == risk["evaluated_rows"]
                 for r in ("DESC-AREA-MATCH", "DESC-ROOMS-MATCH", "DESC-FLOOR-MATCH", "DESC-DISTRICT-MATCH")) else []),
        "**Detection of injected inconsistencies** (synthetic defects; recall with 95% Wilson interval):", "",
        "| Experiment | Rule | Detected / n | Rate | 95% CI |", "|---|---|---|---|---|",
        *[f"| {k.replace('_', ' ')} | {e['rule']} | {e['detected']:,} / {e['n']:,} | {e['rate']:.1%} | {e['ci95_low']:.1%}-{e['ci95_high']:.1%} |"
          for k, e in risk["injected_defects"].items() if "rate" in e and e["rate"] is not None], "",
        f"False flags on consistent synthetic text: {sum(risk['injected_defects']['consistent_synthetic_text_false_flags']['false_flags_by_rule'].values())} "
        f"of {risk['injected_defects']['consistent_synthetic_text_false_flags']['n']:,} rows. With coordinates removed, "
        f"{risk['injected_defects']['coordinates_removed']['facts_unknown']['rate']:.0%} of rows give `unknown` proximity "
        "facts and no geographic flags.", "",
        "![Rule validation](rule_validation.png)", "",
        "## 7. Limitations", "",
        *[f"- {x}" for x in summary["limitations"]], "",
        "## 8. Ethical and practical notes", "",
        "- A flagged listing is a prompt for human review with the evidence shown; the decision stays with the reviewer.",
        "- Prices of expensive or unusual homes are least reliable (see the per-district and large-error sections of the B04 report).",
        "- Coordinates are approximate map pins; district labels come from the source and can be wrong.", "",
        "## 9. Reproduce", "",
        "```", manifest["command"], "```", "",
        "Inputs are hashed in `manifest.json`; the command fails if the B04 model, B05 calibration, B07 package and "
        "snapshot do not belong together. Full build chain (each step is in docs/B04-*, B05, B07):", "",
        "```",
        "python -m ml.train_compare --snapshot data/processed/<dataset> --version <v>",
        "python -m ml.calibrate_intervals --b04 artifacts/b04/<v> --snapshot data/processed/<dataset> --version <v>",
        "python -m ml.package_inference --b04 artifacts/b04/<v> --b05 artifacts/b05/<v> --snapshot data/processed/<dataset> --version <v>",
        "```", ""]
    return "\n".join(lines)


def build_limitations(summary: Mapping[str, Any]) -> List[str]:
    p, risk = summary["price_error"], summary["risk_rules"]
    sens = {x["price_multiplier"]: x["rate"] for x in risk["price_anomaly_sensitivity"]["points"]}
    out = []
    if not p["temporal_split"]:
        out.append("The split is not chronological (one-date scrape): metrics are in-time estimates, optimistic for "
                   "future listings, and real interval coverage can be lower after the market shifts.")
    if not p["targets"]["width_ratio_target"]["met"]:
        out.append(f"Intervals are wide (median width {p['targets']['width_ratio_target']['observed_median_width_ratio_at_0.95']:.2f} "
                   f"of the price versus the provisional target {p['targets']['width_ratio_target']['value']}); they "
                   "reflect how noisy asking rents are given the available features.")
    out += [
        "Asking prices only; no signed rents. Renovation is always null in the A06 export, so it carries no signal.",
        "Coverage is a marginal average, not a guarantee per listing, district or price level.",
        "Listings from the same building can sit in both calibration and test, which makes coverage slightly optimistic.",
        f"The price-anomaly rule flags only large deviations: raising an asking price to 1.5x its actual value is flagged "
        f"for {sens.get(1.5, 0):.0%} of listings, and 2x for {sens.get(2.0, 0):.0%}.",
        "Rule validation uses injected synthetic defects, and near-perfect detection of them is expected by construction: "
        "it shows the rules fire as designed, not that real errors look like these. No fraud labels exist, so fraud precision, recall and false "
        "positive rate on real listings are unmeasured and must not be inferred from this card.",
        "Description-consistency rules cannot be evaluated on real text: the scrape parses fields from the title.",
        "The district check compares labels with where other listings carry that label (no district polygons); it cannot "
        "tell whether the label or the pin is wrong.",
        "Proximity price differences are descriptive and confounded by district, area and building quality.",
        "Thresholds (3 comparables, 60 days, coverage box, rule parameters) are provisional and await owner confirmation.",
    ]
    return out


# --------------------------------------------------------------------------------- main


def run(args: argparse.Namespace) -> Dict[str, Any]:
    inputs = load_inputs(args.b04, args.b05, args.package, args.snapshot)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    pred = predictions(inputs)
    package = inputs["package"]
    summary: Dict[str, Any] = {"evidence_version": EVIDENCE_VERSION, "seed": SEED,
                               "price_error": price_section(inputs), "price_anomaly": price_anomaly_section(pred),
                               "risk_rules": risk_validation(inputs, pred), "ontology": ontology_evaluation(inputs, pred),
                               "proximity_price_effect": vp.metro_proximity_effect(inputs["splits"]["test"], seed=SEED)}
    summary["limitations"] = build_limitations(summary)
    sums = {n: _sha256(d / n) for d, names in ((args.b04, ("model.cbm", "metadata.json", "report.json")),
                                               (args.b05, ("interval_calibration.json", "b05_report.json")),
                                               (args.package, ("package.json", "SHA256SUMS.json"))) for n in names
            for d in (d,)}
    command = ("python -m ml.evaluation_evidence --b04 {} --b05 {} --package {} --snapshot {} --output {}"
               .format(*(str(x).replace("\\", "/") for x in (args.b04, args.b05, args.package, args.snapshot, out))))
    manifest = {"evidence_version": EVIDENCE_VERSION, "command": command,
                "versions": {"package_version": package.manifest["package_version"],
                             "interface_version": package.manifest["interface_version"],
                             "model_version": package.manifest["model_version"],
                             "calibration_version": package.manifest["calibration_version"],
                             "rules_version": package.manifest["rules_version"],
                             "geography_version": package.manifest.get("geography_version"),
                             "dataset_version": package.manifest.get("dataset_version"),
                             "data_as_of": package.manifest["data_as_of"]},
                "calibration": {"method": inputs["report05"]["metadata"]["method"],
                                "primary_level": inputs["report05"]["metadata"]["primary_level"]},
                "inputs": {"snapshot_sha256": inputs["manifest"]["snapshot_sha256"], "model_sha256": inputs["model_sha"],
                           "files_sha256": dict(sorted(sums.items()))}}
    dump = lambda name, obj: (out / name).write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n",  # noqa: E731
                                                      encoding="utf-8")
    charts = make_charts(summary, pred, out)
    manifest["files"] = sorted(["model_card.md", "evaluation_summary.json", "risk_rule_validation.json",
                                "ontology_evaluation.json", *charts])
    dump("evaluation_summary.json", {k: v for k, v in summary.items() if k not in ("risk_rules", "ontology")})
    dump("risk_rule_validation.json", summary["risk_rules"])
    dump("ontology_evaluation.json", summary["ontology"])
    dump("manifest.json", manifest)
    (out / "model_card.md").write_text(model_card(summary, manifest), encoding="utf-8")
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ("b04", "b05", "package", "snapshot"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("docs/evidence/b08"))
    args = parser.parse_args(argv)
    try:
        run(args)
    except (ci.ArtifactError, iv.CalibrationError, inf.PackageError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(f"evidence written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
