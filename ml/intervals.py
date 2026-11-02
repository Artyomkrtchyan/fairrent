"""[B05] Calibrated prediction intervals, ``price_status`` and the serving gate.

Pure numpy/pandas (no CatBoost), so the B07 inference package can load a calibration
without the training dependencies.

Method: split conformal prediction. Non-conformity scores come from a held-out calibration
set (the A06 *validation* split) and never from test labels. With ``n`` scores the interval
uses the ``ceil((n + 1) * level)``-th smallest score, which gives marginal coverage
``>= level`` when calibration and serving rows are exchangeable. See docs/B05-interval-calibration.md
for what that does and does not guarantee.

Contract rules implemented here (ml/CONTRACT.md section 2, docs/contract-semantics.md):
  * an interval is returned only with a calibrated, supported method; otherwise all four
    interval fields are ``null`` and ``calibration_version`` is absent;
  * the bounds enclose the expected price and ``interval_width_usd == upper - lower``;
  * ``price_status`` is one of within_range / above_range / below_range / insufficient_data,
    with inclusive edges counted as within_range.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

CALIBRATION_SCHEMA_VERSION = "b05-v1"
DEFAULT_LEVELS = (0.80, 0.90, 0.95)
PRIMARY_LEVEL = 0.95
METHODS = ("absolute", "relative", "relative_by_district")
PRICE_STATUSES = ("within_range", "above_range", "below_range", "insufficient_data")
MIN_PRED_USD = 1.0  # floor for the centre of an interval / denominator of relative scores

# Serving-gate reason codes (stable strings; B07 and the backend may expose them).
REASON_MISSING_COORDINATES = "missing_or_invalid_coordinates"
REASON_NO_AREA = "coordinate_only_no_calibrated_interval"
REASON_AREA_RANGE = "area_outside_training_range"
REASON_SPARSE = "sparse_local_training_data"
REASON_LOW_PREDICTION = "prediction_below_minimum"


class CalibrationError(ValueError):
    """Raised when an interval cannot be calibrated honestly (for example too few scores)."""


def level_key(level: float) -> str:
    return f"{float(level):.2f}"


def min_calibration_size(level: float) -> int:
    """Smallest n for which the finite-sample conformal quantile exists at ``level``."""
    if not 0 < level < 1:
        raise ValueError("level must be strictly between 0 and 1")
    return math.ceil(round(level / (1 - level), 9))


def conformal_quantile(scores: Iterable[float], level: float) -> float:
    """The ``ceil((n+1)*level)``-th smallest score (finite-sample corrected)."""
    values = np.sort(np.asarray(list(scores), dtype=float))
    values = values[np.isfinite(values)]
    n = len(values)
    needed = min_calibration_size(level)
    if n < needed:
        raise CalibrationError(
            f"{n} calibration scores cannot support a {level:.0%} interval (needs at least {needed}).")
    return float(values[math.ceil((n + 1) * level) - 1])


def nonconformity(y: Sequence[float], pred: Sequence[float], method: str) -> np.ndarray:
    """Absolute error (``absolute``) or error relative to the prediction (``relative*``)."""
    if method not in METHODS:
        raise ValueError(f"method must be one of {METHODS}, got {method!r}")
    y_arr = np.asarray(y, dtype=float)
    centre = np.maximum(np.asarray(pred, dtype=float), MIN_PRED_USD)
    error = np.abs(y_arr - centre)
    return error if method == "absolute" else error / centre


def interval_bounds(pred: Sequence[float] | float, quantile: float, method: str) -> Tuple[np.ndarray, np.ndarray]:
    """Unrounded (lower, upper) USD bounds around ``pred``; lower is clipped at 0."""
    centre = np.maximum(np.atleast_1d(np.asarray(pred, dtype=float)), MIN_PRED_USD)
    half = quantile if method == "absolute" else quantile * centre
    return np.maximum(centre - half, 0.0), centre + half


@dataclass
class IntervalCalibration:
    """Frozen, serialisable result of calibrating one fitted model."""

    method: str
    levels: Dict[str, float]                      # global quantile per level
    n_calibration: int
    primary_level: float = PRIMARY_LEVEL
    calibration_version: str = "uncalibrated"
    group_levels: Dict[str, Dict[str, float]] = field(default_factory=dict)  # relative_by_district only
    group_sizes: Dict[str, int] = field(default_factory=dict)
    min_group_size: int = 100
    meta: Dict[str, Any] = field(default_factory=dict)

    def quantile(self, level: Optional[float] = None, group: Optional[str] = None) -> float:
        key = level_key(self.primary_level if level is None else level)
        if key not in self.levels:
            raise CalibrationError(f"level {key} was not calibrated (have {sorted(self.levels)})")
        if self.method == "relative_by_district" and group in self.group_levels:
            return self.group_levels[group][key]
        return self.levels[key]

    def bounds(self, pred: Sequence[float] | float, level: Optional[float] = None,
               group: Optional[str] = None) -> Tuple[np.ndarray, np.ndarray]:
        base = "relative" if self.method == "relative_by_district" else self.method
        return interval_bounds(pred, self.quantile(level, group), base)

    def to_json(self) -> dict:
        return {
            "calibration_schema_version": CALIBRATION_SCHEMA_VERSION,
            "calibration_version": self.calibration_version,
            "method": self.method,
            "score": ("abs(y - pred)" if self.method == "absolute"
                      else f"abs(y - pred) / max(pred, {MIN_PRED_USD})"),
            "levels": self.levels,
            "primary_level": self.primary_level,
            "n_calibration": self.n_calibration,
            "group_levels": self.group_levels,
            "group_sizes": self.group_sizes,
            "min_group_size": self.min_group_size,
            "meta": self.meta,
        }

    @classmethod
    def from_json(cls, payload: dict) -> "IntervalCalibration":
        if payload.get("calibration_schema_version") != CALIBRATION_SCHEMA_VERSION:
            raise CalibrationError(
                f"unsupported calibration schema {payload.get('calibration_schema_version')!r}")
        return cls(
            method=payload["method"], levels={k: float(v) for k, v in payload["levels"].items()},
            n_calibration=int(payload["n_calibration"]), primary_level=float(payload["primary_level"]),
            calibration_version=payload["calibration_version"],
            group_levels={g: {k: float(v) for k, v in d.items()} for g, d in payload.get("group_levels", {}).items()},
            group_sizes={g: int(v) for g, v in payload.get("group_sizes", {}).items()},
            min_group_size=int(payload.get("min_group_size", 100)), meta=payload.get("meta", {}))


def fit_calibration(y: Sequence[float], pred: Sequence[float], *, method: str = "relative",
                    groups: Optional[Sequence[Any]] = None, levels: Sequence[float] = DEFAULT_LEVELS,
                    primary_level: float = PRIMARY_LEVEL, min_group_size: int = 100,
                    calibration_version: str = "uncalibrated",
                    meta: Optional[Dict[str, Any]] = None) -> IntervalCalibration:
    """Calibrate on held-out ``y`` / ``pred`` (never test labels).

    ``relative_by_district`` (Mondrian conformal) fits a separate quantile for every group of at
    least ``min_group_size`` calibration rows and falls back to the global quantile otherwise.
    """
    if method not in METHODS:
        raise ValueError(f"method must be one of {METHODS}, got {method!r}")
    if primary_level not in levels:
        raise ValueError("primary_level must be one of the calibrated levels")
    scores = nonconformity(y, pred, method)
    ok = np.isfinite(scores)
    if not ok.all():
        raise CalibrationError(f"{int((~ok).sum())} non-finite calibration scores")
    global_levels = {level_key(lv): conformal_quantile(scores, lv) for lv in levels}
    group_levels: Dict[str, Dict[str, float]] = {}
    group_sizes: Dict[str, int] = {}
    if method == "relative_by_district":
        if groups is None:
            raise ValueError("relative_by_district needs groups")
        group_arr = np.asarray(["unresolved" if g is None or (isinstance(g, float) and math.isnan(g)) else str(g)
                                for g in groups])
        for name in sorted(set(group_arr)):
            mask = group_arr == name
            group_sizes[name] = int(mask.sum())
            if mask.sum() < min_group_size:
                continue
            try:
                group_levels[name] = {level_key(lv): conformal_quantile(scores[mask], lv) for lv in levels}
            except CalibrationError:
                continue
    return IntervalCalibration(
        method=method, levels=global_levels, n_calibration=int(len(scores)), primary_level=primary_level,
        calibration_version=calibration_version, group_levels=group_levels, group_sizes=group_sizes,
        min_group_size=min_group_size, meta=dict(meta or {}))


# ------------------------------------------------------------------ response blocks


def _floor_cents(value: float) -> float:
    return math.floor(round(value * 100, 6)) / 100


def _ceil_cents(value: float) -> float:
    return math.ceil(round(value * 100, 6)) / 100


def prediction_reasons(pred_usd: Sequence[float] | float) -> List[List[str]]:
    """Reason codes per prediction: a prediction under ``MIN_PRED_USD`` (or not finite) gets no interval.

    Relative scores are undefined around a near-zero centre, and the interval would have to
    exclude the expected price (centres are floored at ``MIN_PRED_USD``). Withholding keeps the
    contract rule ``lower <= expected <= upper`` true for every interval that is returned.
    """
    values = np.atleast_1d(np.asarray(pred_usd, dtype=float))
    return [[] if (np.isfinite(v) and v >= MIN_PRED_USD) else [REASON_LOW_PREDICTION] for v in values]


def null_interval() -> Dict[str, Any]:
    """The contract's four interval fields, all null (no calibration_version key)."""
    return {"lower_bound_usd": None, "upper_bound_usd": None, "confidence_level": None,
            "interval_width_usd": None}


def prediction_interval(pred_usd: Optional[float], calibration: Optional[IntervalCalibration], *,
                        level: Optional[float] = None, group: Optional[str] = None,
                        reasons: Sequence[str] = ()) -> Dict[str, Any]:
    """The ``ml_prediction_interval`` block.

    Returns the all-null block when there is no calibration, no prediction, a prediction below
    ``MIN_PRED_USD`` (see ``prediction_reasons``), or the serving gate reported any reason to withhold. Bounds are rounded outward to whole cents so rounding can
    never break coverage or the ``lower <= expected <= upper`` rule, and ``interval_width_usd``
    is computed from the rounded bounds so it always equals upper minus lower.
    """
    if (calibration is None or reasons or pred_usd is None
            or not isinstance(pred_usd, (int, float)) or not math.isfinite(pred_usd)
            or pred_usd < MIN_PRED_USD):
        return null_interval()
    lower, upper = calibration.bounds(pred_usd, level, group)
    lo, hi = _floor_cents(float(lower[0])), _ceil_cents(float(upper[0]))
    return {
        "lower_bound_usd": lo, "upper_bound_usd": hi,
        "confidence_level": float(calibration.primary_level if level is None else level),
        "interval_width_usd": round(hi - lo, 2),
        "calibration_version": calibration.calibration_version,
    }


def price_status(asking_price_usd: Optional[float], interval: Optional[Dict[str, Any]] = None, *,
                 lower: Optional[float] = None, upper: Optional[float] = None) -> str:
    """within_range / above_range / below_range / insufficient_data.

    Pass either the ``ml_prediction_interval`` block or explicit ``lower``/``upper``. Missing,
    non-finite or non-positive asking price, or any missing bound, is ``insufficient_data``.
    Edges are inclusive: ``lower <= asking <= upper`` is within_range.
    """
    if interval is not None:
        lower, upper = interval.get("lower_bound_usd"), interval.get("upper_bound_usd")
    values = (asking_price_usd, lower, upper)
    if any(v is None or isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
           for v in values):
        return "insufficient_data"
    if asking_price_usd <= 0:
        return "insufficient_data"
    if lower > upper:
        raise ValueError(f"lower bound {lower} is above upper bound {upper}")
    if asking_price_usd < lower:
        return "below_range"
    if asking_price_usd > upper:
        return "above_range"
    return "within_range"


# --------------------------------------------------------------------- serving gate


def _cell(lat: float, lon: float, size: float) -> Tuple[int, int]:
    return math.floor(lat / size), math.floor(lon / size)


@dataclass
class ServingGate:
    """When NOT to return a calibrated interval. Fitted on the training split only.

    Rules are fixed in advance on principle (contract + support), not tuned on test labels:
      * invalid coordinates                      -> no interval;
      * area unknown (coordinate-only request)   -> no interval (contract: not separately calibrated);
      * area outside the training range          -> no interval (extrapolation);
      * fewer than ``min_local_train`` training listings in the 3x3 grid block around the point
        -> no interval (sparse local data; mirrors the provisional "< 3 comparables" rule).
    Training coordinates are stored as grid-cell counts, not as raw points.
    """

    area_min: float
    area_max: float
    cell_size_deg: float
    min_local_train: int
    cell_counts: Dict[str, int]
    area_quantiles: Tuple[float, float] = (0.005, 0.995)

    @classmethod
    def fit(cls, train: pd.DataFrame, *, cell_size_deg: float = 0.01, min_local_train: int = 3,
            area_quantiles: Tuple[float, float] = (0.005, 0.995)) -> "ServingGate":
        area = pd.to_numeric(train["area_sqm"], errors="coerce").dropna()
        area = area[area > 0]
        if area.empty:
            raise CalibrationError("training split has no usable area_sqm to fit the serving gate")
        lat = pd.to_numeric(train["latitude"], errors="coerce")
        lon = pd.to_numeric(train["longitude"], errors="coerce")
        counts: Dict[str, int] = {}
        for la, lo in zip(lat[lat.notna() & lon.notna()], lon[lat.notna() & lon.notna()]):
            ix, iy = _cell(float(la), float(lo), cell_size_deg)
            counts[f"{ix},{iy}"] = counts.get(f"{ix},{iy}", 0) + 1
        return cls(area_min=float(area.quantile(area_quantiles[0])), area_max=float(area.quantile(area_quantiles[1])),
                   cell_size_deg=cell_size_deg, min_local_train=min_local_train, cell_counts=counts,
                   area_quantiles=area_quantiles)

    def local_support(self, lat: float, lon: float) -> int:
        ix, iy = _cell(lat, lon, self.cell_size_deg)
        return sum(self.cell_counts.get(f"{ix + dx},{iy + dy}", 0) for dx in (-1, 0, 1) for dy in (-1, 0, 1))

    def reasons(self, frame: pd.DataFrame) -> List[List[str]]:
        """Reason codes per row (empty list = an interval may be returned)."""
        lat = pd.to_numeric(frame["latitude"], errors="coerce").to_numpy(dtype=float)
        lon = pd.to_numeric(frame["longitude"], errors="coerce").to_numpy(dtype=float)
        area = pd.to_numeric(frame["area_sqm"], errors="coerce").to_numpy(dtype=float)
        out: List[List[str]] = []
        for la, lo, ar in zip(lat, lon, area):
            row: List[str] = []
            if not (math.isfinite(la) and math.isfinite(lo) and -90 <= la <= 90 and -180 <= lo <= 180):
                row.append(REASON_MISSING_COORDINATES)
            if not math.isfinite(ar) or ar <= 0:
                row.append(REASON_NO_AREA)
            elif not self.area_min <= ar <= self.area_max:
                row.append(REASON_AREA_RANGE)
            if REASON_MISSING_COORDINATES not in row and self.local_support(la, lo) < self.min_local_train:
                row.append(REASON_SPARSE)
            out.append(row)
        return out

    def to_json(self) -> dict:
        return {"area_min": self.area_min, "area_max": self.area_max, "area_quantiles": list(self.area_quantiles),
                "cell_size_deg": self.cell_size_deg, "min_local_train": self.min_local_train,
                "cell_counts": self.cell_counts, "fitted_on": "train split only",
                "rules": [REASON_MISSING_COORDINATES, REASON_NO_AREA, REASON_AREA_RANGE, REASON_SPARSE]}

    @classmethod
    def from_json(cls, payload: dict) -> "ServingGate":
        return cls(area_min=float(payload["area_min"]), area_max=float(payload["area_max"]),
                   cell_size_deg=float(payload["cell_size_deg"]), min_local_train=int(payload["min_local_train"]),
                   cell_counts={str(k): int(v) for k, v in payload["cell_counts"].items()},
                   area_quantiles=tuple(payload.get("area_quantiles", (0.005, 0.995))))


# ----------------------------------------------------------------------- metrics


def interval_metrics(y: Sequence[float], pred: Sequence[float], lower: Sequence[float],
                     upper: Sequence[float]) -> Dict[str, Any]:
    """Empirical coverage and width of intervals against true prices."""
    y_arr, pred_arr = np.asarray(y, float), np.maximum(np.asarray(pred, float), MIN_PRED_USD)
    lo, hi = np.asarray(lower, float), np.asarray(upper, float)
    n = int(len(y_arr))
    if n == 0:
        return {"n": 0, "coverage": None, "mean_width_usd": None, "median_width_usd": None,
                "median_width_ratio": None, "mean_width_ratio": None}
    width = hi - lo
    ratio = width / pred_arr
    return {"n": n, "coverage": round(float(((y_arr >= lo) & (y_arr <= hi)).mean()), 4),
            "mean_width_usd": round(float(width.mean()), 2), "median_width_usd": round(float(np.median(width)), 2),
            "median_width_ratio": round(float(np.median(ratio)), 4), "mean_width_ratio": round(float(ratio.mean()), 4)}


def dumps(payload: dict) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, default=str)
