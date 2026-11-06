"""B09: coordinate-based observed-price statistics and assessment (Pandas + scikit-learn).

Reference pipeline with explicit, versioned cohort rules. It never invents values:
below the minimum sample it abstains, and observed dispersion (sample std, n-1) is
never presented as a prediction interval.

Rules (RULES_VERSION):
  1. Inventory: one observation per listing, dated by ``last_seen_at`` (active at ``as_of``).
  2. Window: inclusive Asia/Yerevan local dates [as_of_date - window_days + 1, as_of_date],
     window_days capped at 60.
  3. Radius: geodesic (haversine) distance <= radius_m, boundary inclusive.
  4. Eligibility first (rooms exact, optional district), THEN duplicates:
     latest observation per dedup group; ties by listing_id ascending;
     ungrouped listings count once each.
  5. No silent widening; effective cohort metadata is always returned.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

RULES_VERSION = "b09-cohort-v1"
EARTH_RADIUS_M = 6371000.0
LOCAL_TZ = ZoneInfo("Asia/Yerevan")
MAX_WINDOW_DAYS = 60
MAX_RADIUS_M = 5000
COVERAGE_BBOX = {"south": 40.05, "north": 40.30, "west": 44.35, "east": 44.66}  # provisional
REQUIRED = ("listing_id", "price_usd", "latitude", "longitude", "last_seen_at", "status")
ACTIVE_STATUS = "active"


class OutsideCoverage(ValueError):
    pass


@dataclass(frozen=True)
class CohortRules:
    radius_m: int = 1000
    window_days: int = 30
    minimum_sample_size: int = 3  # provisional: owner must confirm
    version: str = RULES_VERSION

    def validate(self) -> None:
        if not 0 < self.radius_m <= MAX_RADIUS_M:
            raise ValueError(f"radius_m must be in (0, {MAX_RADIUS_M}]")
        if not 1 <= self.window_days <= MAX_WINDOW_DAYS:
            raise ValueError(f"window_days must be in [1, {MAX_WINDOW_DAYS}]")
        if self.minimum_sample_size < 2:
            raise ValueError("minimum_sample_size must be >= 2 (sample std needs n-1 > 0)")


def check_coverage(latitude: float, longitude: float) -> None:
    b = COVERAGE_BBOX
    if not (b["south"] <= latitude <= b["north"] and b["west"] <= longitude <= b["east"]):
        raise OutsideCoverage("Coordinates are outside the supported coverage area")


def _timestamps(values: pd.Series) -> pd.Series:
    """ISO-8601 with mixed precision (whole seconds, milliseconds, offsets) in one column."""
    return pd.to_datetime(values, utc=True, errors="coerce", format="ISO8601")


def _prepare(listings: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in REQUIRED if c not in listings.columns]
    if missing:
        raise ValueError(f"listings missing columns: {missing}")
    f = listings.copy()
    f["listing_id"] = f["listing_id"].astype(str)
    for c in ("price_usd", "latitude", "longitude"):
        f[c] = pd.to_numeric(f[c], errors="coerce")
    f["area_sqm"] = pd.to_numeric(f["area_sqm"], errors="coerce") if "area_sqm" in f else np.nan
    f["last_seen_at"] = _timestamps(f["last_seen_at"])
    if "dedup_group_id" not in f:
        f["dedup_group_id"] = None
    # Ungrouped (None/NaN/empty) listings count once, keyed by listing id.
    grouped = f["dedup_group_id"].notna() & f["dedup_group_id"].astype(str).str.strip().ne("")
    f["_key"] = np.where(grouped, "group:" + f["dedup_group_id"].astype(str), "listing:" + f["listing_id"])
    # Active inventory: status must be 'active'; an optional ended_at <= as_of also excludes.
    active = f["status"].astype(str).str.strip().str.casefold().eq(ACTIVE_STATUS)
    f["_active"] = active
    ok = (f.price_usd.gt(0) & np.isfinite(f.price_usd) & f.latitude.between(-90, 90)
          & f.longitude.between(-180, 180) & f.last_seen_at.notna())
    # Unusable area is treated as unknown, not as an error: monthly stats still count it.
    f.loc[~(f.area_sqm.gt(0) & np.isfinite(f.area_sqm)), "area_sqm"] = np.nan
    return f.loc[ok]


def select_cohort(listings: pd.DataFrame, latitude: float, longitude: float, *, as_of: datetime,
                  rules: CohortRules = CohortRules(), rooms: Optional[int] = None,
                  district: Optional[str] = None,
                  exclude_group: Optional[str] = None) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    rules.validate()
    if as_of.tzinfo is None:
        raise ValueError("as_of must have a timezone")
    # Caller index labels are meaningless (may repeat); positional labels keep every filter aligned.
    listings = listings.reset_index(drop=True)
    f = _prepare(listings)
    for name, col in (("rooms", rooms), ("district", district)):
        if col is not None and col != "" and name not in listings.columns:
            raise ValueError(f"{name} filter requested but listings has no '{name}' column")
    counts = {"input": int(len(listings)), "valid": int(len(f))}
    if "ended_at" in listings.columns:
        raw = listings["ended_at"]
        ended = _timestamps(raw)
        bad = raw.notna() & raw.astype(str).str.strip().ne("") & ended.isna()
        if bad.any():  # fail closed: never keep a listing because its end time is unreadable
            raise ValueError(f"ended_at has {int(bad.sum())} unparseable value(s)")
        f = f.loc[~(ended.reindex(f.index).le(pd.Timestamp(as_of)).fillna(False))]
    f = f.loc[f["_active"]]
    counts["active"] = int(len(f))
    end = as_of.astimezone(LOCAL_TZ).date()
    start = end - timedelta(days=rules.window_days - 1)
    local_date = f["last_seen_at"].dt.tz_convert(LOCAL_TZ).dt.date
    f = f.loc[(local_date >= start) & (local_date <= end) & (f["last_seen_at"] <= pd.Timestamp(as_of))]
    counts["in_window"] = int(len(f))
    if len(f):
        tree = BallTree(np.radians(f[["latitude", "longitude"]].to_numpy()), metric="haversine")
        # Exact distance for every row so the inclusive boundary is decided on one number.
        dist = tree.query(np.radians([[latitude, longitude]]), k=len(f))
        d = pd.Series(dist[0][0] * EARTH_RADIUS_M, index=f.index[dist[1][0]])
        f = f.assign(distance_m=d.reindex(f.index))
        f = f.loc[f.distance_m <= rules.radius_m]
    else:
        f = f.assign(distance_m=pd.Series(dtype=float))
    counts["in_radius"] = int(len(f))
    if exclude_group is not None:
        f = f.loc[f["_key"] != "group:" + str(exclude_group)]
    if rooms is not None:
        f = f.loc[pd.to_numeric(f.get("rooms"), errors="coerce") == rooms]
    if district:
        f = f.loc[f.get("district").astype(str).str.casefold() == district.casefold()]
    counts["eligible"] = int(len(f))
    f = f.sort_values(["last_seen_at", "listing_id"], ascending=[False, True], kind="stable")
    f = f.drop_duplicates("_key", keep="first")
    counts["after_duplicates"] = int(len(f))
    meta = dict(radius_m=rules.radius_m, window_days=rules.window_days,
                period_start=str(start), period_end=str(end),
                minimum_sample_size=rules.minimum_sample_size, selection_version=rules.version,
                duplicate_policy="latest_observation_per_duplicate_group",
                inventory_policy="active_at_data_as_of",
                rooms_filter=rooms, district_filter=district, counts=counts)
    return f.drop(columns=["_key", "_active"]), meta


def _std(values: pd.Series) -> Optional[float]:
    return float(values.std(ddof=1)) if len(values) > 1 else None


def summarize(cohort: pd.DataFrame) -> Dict[str, Any]:
    prices = cohort["price_usd"]
    unit = (cohort["price_usd"] / cohort["area_sqm"]).dropna()
    return dict(
        comparables_count=int(len(prices)),
        cluster_mean_price_usd=float(prices.mean()) if len(prices) else None,
        observed_price_std_dev_usd=_std(prices),
        area_comparables_count=int(len(unit)),
        cluster_mean_price_per_sqm_usd=float(unit.mean()) if len(unit) else None,
        observed_price_std_dev_per_sqm_usd=_std(unit),
        std_dev_basis="sample (n-1); observed dispersion of comparables, NOT a prediction interval")


def assess_market(listings: pd.DataFrame, latitude: float, longitude: float, *, as_of: datetime,
                  rules: CohortRules = CohortRules(), area_sqm: Optional[float] = None,
                  rooms: Optional[int] = None, district: Optional[str] = None,
                  asking_price_usd: Optional[float] = None,
                  exclude_group: Optional[str] = None) -> Dict[str, Any]:
    """Coordinate-only reference when area/rooms are missing; property-specific otherwise."""
    check_coverage(latitude, longitude)
    if area_sqm is not None and not (np.isfinite(area_sqm) and area_sqm > 0):
        raise ValueError("area_sqm must be finite and positive")
    cohort, meta = select_cohort(listings, latitude, longitude, as_of=as_of, rules=rules,
                                 rooms=rooms, district=district, exclude_group=exclude_group)
    stats = summarize(cohort)
    n, k = stats["comparables_count"], rules.minimum_sample_size
    property_specific = area_sqm is not None and rooms is not None
    out = dict(cohort=meta, observed_market_statistics=stats, prediction_interval=None,
               data_as_of=(cohort["last_seen_at"].max().isoformat() if n else None))
    if n < k:
        out["assessment"] = dict(status="INSUFFICIENT_DATA_ABSTAIN", mode=None, estimated_price_usd=None,
                                 reason=f"{n} comparable(s) < minimum {k}")
        return out
    if not property_specific:
        out["assessment"] = dict(status="COORDINATE_BASELINE_ONLY", mode="coordinate_reference",
                                 estimated_price_usd=stats["cluster_mean_price_usd"],
                                 reason="area and/or rooms not supplied; value is the observed cohort mean")
        return out
    if stats["area_comparables_count"] < k:
        out["assessment"] = dict(status="INSUFFICIENT_DATA_ABSTAIN", mode="property_specific",
                                 estimated_price_usd=None,
                                 reason=f"{stats['area_comparables_count']} comparable(s) with area < minimum {k}")
        return out
    est = stats["cluster_mean_price_per_sqm_usd"] * area_sqm
    sd = stats["observed_price_std_dev_per_sqm_usd"] * area_sqm
    a = dict(status="ASSESSED", mode="property_specific", estimated_price_usd=float(est),
             observed_dispersion_usd=float(sd),
             reason="mean USD/m2 of comparables x subject area; dispersion is observed, not predictive")
    if asking_price_usd is not None:
        a["asking_price_position"] = ("below_observed_mean_minus_1sd" if asking_price_usd < est - sd else
                                      "above_observed_mean_plus_1sd" if asking_price_usd > est + sd else
                                      "within_observed_1sd")
    out["assessment"] = a
    return out


def _cli() -> None:
    import argparse, json
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("csv"); p.add_argument("--lat", type=float, required=True)
    p.add_argument("--lon", type=float, required=True); p.add_argument("--as-of", required=True)
    p.add_argument("--radius-m", type=int, default=1000); p.add_argument("--window-days", type=int, default=30)
    p.add_argument("--area", type=float); p.add_argument("--rooms", type=int)
    a = p.parse_args()
    try:
        res = _run(a)
    except (ValueError, OutsideCoverage) as exc:
        raise SystemExit(f"error: {exc}")
    print(json.dumps(res, indent=2, default=str))


def _run(a):
    return assess_market(pd.read_csv(a.csv), a.lat, a.lon, as_of=datetime.fromisoformat(a.as_of),
                        rules=CohortRules(a.radius_m, a.window_days), area_sqm=a.area, rooms=a.rooms)


if __name__ == "__main__":
    _cli()
