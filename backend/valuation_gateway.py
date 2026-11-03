"""C04 adapter for a versioned observed-inventory snapshot, not model training."""
from datetime import datetime
from math import asin, cos, radians, sin, sqrt

import pandas as pd

from ml.baseline import ComparableMedianBaseline


class ModelUnavailable(RuntimeError):
    """Prediction failed; callers must not substitute a successful valuation."""


class BaselineGateway:
    model_version = "b03-23f4244+c04-scope-v2"

    def __init__(self, snapshot, *, dataset_version, predictor=ComparableMedianBaseline):
        if not dataset_version:
            raise ValueError("A reference dataset version is required")
        required = {"price_usd", "area_sqm", "latitude", "longitude",
                    "district", "rooms", "listing_date", "dedup_group_id"}
        if not required.issubset(snapshot.columns):
            raise ValueError("Reference snapshot is missing required columns")
        self.snapshot = snapshot.copy(deep=True)
        self.dataset_version = dataset_version
        self.predictor = predictor

    def assess(self, payload, *, as_of: datetime, radius_m=1000, window_days=60,
               exclude_group=None):
        if as_of.tzinfo is None:
            raise ValueError("as_of must have a timezone")
        lat, lon = payload.get("latitude"), payload.get("longitude")
        if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("Valid coordinates are required")
        if not 0 < radius_m <= 5000 or not 1 <= window_days <= 90:
            raise ValueError("Invalid comparable radius or age window")
        area = payload.get("area_sqm")
        if area is not None and (not pd.notna(area) or not 0 < area < float("inf")):
            raise ValueError("area_sqm must be finite and positive")
        frame = self.snapshot.copy(deep=True)
        frame["listing_date"] = pd.to_datetime(frame["listing_date"], utc=True, errors="coerce")
        for column in ("price_usd", "area_sqm", "latitude", "longitude"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        valid = (frame.price_usd.gt(0) & frame.price_usd.lt(float("inf"))
                 & frame.area_sqm.gt(0) & frame.area_sqm.lt(float("inf"))
                 & frame.latitude.between(-90, 90) & frame.longitude.between(-180, 180)
                 & frame.dedup_group_id.notna()
                 & frame.listing_date.between(pd.Timestamp(as_of) - pd.Timedelta(days=window_days),
                                              pd.Timestamp(as_of)))
        frame = frame.loc[valid].copy()
        if exclude_group is not None:
            frame = frame[frame.dedup_group_id != exclude_group]
        def distance(row):
            a = sin(radians(row.latitude - lat) / 2) ** 2 + cos(radians(lat)) * cos(radians(row.latitude)) * sin(radians(row.longitude - lon) / 2) ** 2
            return 6371000 * 2 * asin(sqrt(min(1, max(0, a))))
        if not frame.empty:
            frame = frame[frame.apply(distance, axis=1) <= radius_m]
        district = payload.get("district")
        if district:
            frame = frame[frame.district.str.casefold() == district.casefold()]
        sort_columns = ["listing_date"] + (["listing_id"] if "listing_id" in frame.columns else [])
        frame = frame.sort_values(sort_columns, ascending=[False] + ([True] if len(sort_columns) > 1 else []), kind="stable").drop_duplicates("dedup_group_id")
        rooms = payload.get("rooms")
        matches = frame[frame.rooms == rooms] if rooms is not None else frame
        if rooms is not None:
            frame = matches
        # Always recompute: an incoming price_per_sqm column is not trusted.
        frame["price_per_sqm"] = frame.price_usd / frame.area_sqm
        try:
            result = self.predictor(frame, max_distance_km=radius_m / 1000,
                                    max_freshness_days=60).predict(payload, query_date=as_of.isoformat())
        except Exception as exc:
            raise ModelUnavailable("Baseline prediction failed") from exc
        result["observed_market_statistics"]["data_freshness_days"] = (
            max(0, int((pd.Timestamp(as_of) - frame.listing_date.max()).total_seconds() // 86400))
            if not frame.empty else None
        )
        if area is None:
            result["selection_explanation"] = (
                "Coordinate baseline uses configured reference area 60 sqm; "
                "this is not a fitted district median. "
                f"Selected {len(frame)} comparable duplicate groups."
            )
        result["versions"] = {"model_version": self.model_version,
                              "dataset_version": self.dataset_version}
        result["generated_at"] = as_of.isoformat()
        result["ml_prediction_interval"] = None
        result["feature_attributions"] = []
        result["selection_explanation"] += f" Radius {radius_m} m; window {window_days} days; one observation per duplicate group."
        return result


class PackagedGateway:
    """B07 adapter. A configured but unavailable package never silently uses B03."""

    def __init__(self, snapshot, *, dataset_version):
        self.snapshot = snapshot
        self.dataset_version = dataset_version

    def assess(self, payload, *, as_of, radius_m=1000, window_days=30):
        from ml import inference
        try:
            from .valuation_coverage import OutsideCoverage
        except ImportError:
            from valuation_coverage import OutsideCoverage
        dates = pd.to_datetime(self.snapshot['listing_date'], utc=True, errors='coerce')
        cutoff = dates.max() if dates.notna().any() else as_of
        model_input = {**payload, 'as_of': cutoff.isoformat().replace('+00:00', 'Z'),
                       'radius_m': radius_m, 'window_days': window_days}
        # Only the backend's already selected/deduplicated cohort reaches B07.
        comparables = self.snapshot[['price_usd', 'area_sqm']].to_dict('records')
        try:
            result = inference.assess(model_input, comparables=comparables, now=as_of)
        except inference.OutsideCoverageError as exc:
            raise OutsideCoverage(str(exc)) from exc
        result['selection_explanation'] = result['explanation']
        result['kind'] = inference.kind_for(result)
        return result


def configured_gateway(snapshot, *, dataset_version):
    import os
    gateway = PackagedGateway if os.environ.get('FAIRRENT_MODEL_PACKAGE') else BaselineGateway
    return gateway(snapshot, dataset_version=dataset_version)
