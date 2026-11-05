"""B08: descriptive price-per-m2 comparison by proximity bucket (the 'price effect' B06's rules deliberately do not assume).

The B06 proximity rules only infer location facts. Whether being near a metro station goes with higher rent is an
empirical question, answered here on held-out listings with plain medians and a bootstrap interval. It is descriptive,
not causal: near-metro listings also sit in different districts, have different areas and so on, so the comparison is
repeated inside each district that has enough listings in both buckets.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from ml import ontology_rules as rules

NEAR_M = rules.RULES["GEO-PROX-METRO"].parameters["near_m"]
FAR_M = rules.RULES["GEO-PROX-METRO"].parameters["extended_m"]
MIN_PER_BUCKET = 30
N_BOOT = 2000


def _median_ratio_ci(near: np.ndarray, far: np.ndarray, rng: np.random.Generator) -> Dict[str, float]:
    ratios = np.empty(N_BOOT)
    for i in range(N_BOOT):
        ratios[i] = np.median(rng.choice(near, near.size)) / np.median(rng.choice(far, far.size))
    return {"ratio": float(np.median(near) / np.median(far)),
            "ci95_low": float(np.percentile(ratios, 2.5)), "ci95_high": float(np.percentile(ratios, 97.5))}


def metro_proximity_effect(frame: pd.DataFrame, *, seed: int = 20261104) -> Dict[str, Any]:
    """Median price per m2 near (<= near_m) versus far (> extended_m) from the nearest metro station."""
    geo = rules._geography()
    if geo is None:
        return {"available": False, "reason": "geography registry unavailable"}
    area = pd.to_numeric(frame["area_sqm"], errors="coerce")
    price = pd.to_numeric(frame["price_usd"], errors="coerce")
    lat = pd.to_numeric(frame["latitude"], errors="coerce")
    lon = pd.to_numeric(frame["longitude"], errors="coerce")
    keep = (area > 0) & (price > 0) & lat.notna() & lon.notna()
    work = pd.DataFrame({"ppsqm": (price / area)[keep], "district": frame["district"][keep].astype("object")})
    work["metro_m"] = [geo.proximity_features(float(a), float(b))["distance_metro_m"]
                       for a, b in zip(lat[keep], lon[keep])]
    work = work.dropna(subset=["metro_m"])
    work["bucket"] = np.where(work["metro_m"] <= NEAR_M, "near", np.where(work["metro_m"] > FAR_M, "far", "between"))
    rng = np.random.default_rng(seed)
    buckets = {b: {"n": int((work["bucket"] == b).sum()),
                   "median_price_per_sqm_usd": (round(float(work.loc[work["bucket"] == b, "ppsqm"].median()), 2)
                                                if (work["bucket"] == b).any() else None)}
               for b in ("near", "between", "far")}
    near, far = work.loc[work["bucket"] == "near", "ppsqm"].to_numpy(), work.loc[work["bucket"] == "far", "ppsqm"].to_numpy()
    overall: Optional[Dict[str, float]] = (_median_ratio_ci(near, far, rng)
                                           if near.size >= MIN_PER_BUCKET and far.size >= MIN_PER_BUCKET else None)
    within: List[Dict[str, Any]] = []
    for district, group in work.groupby("district", dropna=True):
        n_arr = group.loc[group["bucket"] == "near", "ppsqm"].to_numpy()
        f_arr = group.loc[group["bucket"] == "far", "ppsqm"].to_numpy()
        if n_arr.size >= MIN_PER_BUCKET and f_arr.size >= MIN_PER_BUCKET:
            within.append({"district": str(district), "n_near": int(n_arr.size), "n_far": int(f_arr.size),
                           **_median_ratio_ci(n_arr, f_arr, rng)})
    return {"available": True, "near_m": NEAR_M, "far_m": FAR_M, "rows": int(len(work)), "buckets": buckets,
            "near_vs_far_overall": overall, "near_vs_far_within_district": within,
            "interpretation": ("Ratio of median price per m2, near / far. Descriptive only: not controlled for area, "
                               "floor or building quality, and not causal. The model's own use of distance features is "
                               "reported separately as feature importance.")}
