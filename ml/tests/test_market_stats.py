from datetime import datetime, timezone
from statistics import stdev

import pandas as pd
import pytest

from ml.market_stats import CohortRules, OutsideCoverage, assess_market, select_cohort, summarize

LAT, LON = 40.18, 44.51
NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


def row(i, price, area=50.0, dlat=0.0, seen="2026-10-30T10:00:00Z", group=None, rooms=2, district="Kentron", status="active"):
    return dict(listing_id=i, price_usd=price, area_sqm=area, latitude=LAT + dlat, longitude=LON,
                last_seen_at=seen, dedup_group_id=group, rooms=rooms, district=district, status=status)


def df(*rows):
    return pd.DataFrame(rows)


KNOWN = df(row("a", 400, 40), row("b", 500, 50), row("c", 600, 60), row("d", 700, 50), row("e", 800, 80))


def test_known_sample_exact_numbers():
    r = assess_market(KNOWN, LAT, LON, as_of=NOW)
    s = r["observed_market_statistics"]
    assert s["comparables_count"] == 5 and s["cluster_mean_price_usd"] == 600
    assert s["observed_price_std_dev_usd"] == pytest.approx(stdev([400, 500, 600, 700, 800]))  # n-1
    units = [10, 10, 10, 14, 10]
    assert s["cluster_mean_price_per_sqm_usd"] == pytest.approx(sum(units) / 5)
    assert s["observed_price_std_dev_per_sqm_usd"] == pytest.approx(stdev(units))
    assert r["prediction_interval"] is None
    assert "NOT a prediction interval" in s["std_dev_basis"]
    assert r["assessment"]["status"] == "COORDINATE_BASELINE_ONLY"
    assert r["assessment"]["estimated_price_usd"] == 600


def test_property_specific_valuation():
    r = assess_market(KNOWN, LAT, LON, as_of=NOW, area_sqm=50, rooms=2, asking_price_usd=1000)
    a = r["assessment"]
    assert a["status"] == "ASSESSED" and a["mode"] == "property_specific"
    assert a["estimated_price_usd"] == pytest.approx(10.8 * 50)
    assert a["asking_price_position"] == "above_observed_mean_plus_1sd"
    assert r["prediction_interval"] is None


def test_sparse_abstains_without_fabrication():
    r = assess_market(KNOWN.head(2), LAT, LON, as_of=NOW)
    assert r["assessment"]["status"] == "INSUFFICIENT_DATA_ABSTAIN"
    assert r["assessment"]["estimated_price_usd"] is None
    assert r["observed_market_statistics"]["observed_price_std_dev_usd"] == pytest.approx(stdev([400, 500]))
    empty = assess_market(KNOWN.iloc[0:0], LAT, LON, as_of=NOW)
    assert empty["observed_market_statistics"]["cluster_mean_price_usd"] is None
    assert empty["data_as_of"] is None


def test_single_comparable_has_no_std():
    s = summarize(select_cohort(KNOWN.head(1), LAT, LON, as_of=NOW)[0])
    assert s["observed_price_std_dev_usd"] is None


def test_out_of_coverage():
    with pytest.raises(OutsideCoverage):
        assess_market(KNOWN, 41.0, LON, as_of=NOW)


def test_radius_inclusive_boundary_and_no_widening():
    c, _ = select_cohort(df(row("x", 1, dlat=0.001)), LAT, LON, as_of=NOW, rules=CohortRules(radius_m=200))
    assert len(c) == 1
    d = float(c.distance_m.iloc[0])
    c, _ = select_cohort(df(row("x", 1, dlat=0.001)), LAT, LON, as_of=NOW, rules=CohortRules(radius_m=int(d)))
    assert len(c) == 0  # 111 m listing excluded at 111 m radius (distance 111.19 m)
    far = df(row("x", 1, dlat=0.05))
    assert len(select_cohort(far, LAT, LON, as_of=NOW)[0]) == 0


def test_window_inclusive_local_dates():
    # as_of 2026-11-01 Yerevan; window 3 days -> 2026-10-30..2026-11-01 local.
    rules = CohortRules(window_days=3)
    inside = row("in", 1, seen="2026-10-29T20:00:00Z")   # 2026-10-30 00:00 local (UTC+4)
    outside = row("out", 1, seen="2026-10-29T19:59:00Z")  # 2026-10-29 23:59 local
    future = row("fut", 1, seen="2026-11-01T12:00:01Z")
    c, meta = select_cohort(df(inside, outside, future), LAT, LON, as_of=NOW, rules=rules)
    assert list(c.listing_id) == ["in"]
    assert meta["period_start"] == "2026-10-30" and meta["period_end"] == "2026-11-01"


def test_duplicates_latest_wins_tie_by_id_and_ungrouped_once():
    rows = [row("z", 100, group="g", seen="2026-10-30T10:00:00Z"),
            row("b", 200, group="g", seen="2026-10-31T10:00:00Z"),
            row("a", 300, group="g", seen="2026-10-31T10:00:00Z"),  # tie with b -> a (id asc)
            row("u1", 400), row("u2", 500, group=None)]
    c, meta = select_cohort(df(*rows), LAT, LON, as_of=NOW)
    assert sorted(c.listing_id) == ["a", "u1", "u2"]
    assert meta["counts"]["eligible"] == 5 and meta["counts"]["after_duplicates"] == 3


def test_eligibility_before_dedup():
    # Latest observation of the group has other rooms; the eligible earlier one must be kept.
    rows = [row("old", 100, group="g", rooms=2, seen="2026-10-29T10:00:00Z"),
            row("new", 900, group="g", rooms=3, seen="2026-10-31T10:00:00Z")]
    c, _ = select_cohort(df(*rows), LAT, LON, as_of=NOW, rooms=2)
    assert list(c.listing_id) == ["old"]


def test_rooms_district_and_exclude_group():
    f = df(row("a", 1, rooms=1), row("b", 2, rooms=2, district="Arabkir"), row("c", 3, rooms=2, group="s"))
    assert sorted(select_cohort(f, LAT, LON, as_of=NOW, rooms=2)[0].listing_id) == ["b", "c"]
    assert sorted(select_cohort(f, LAT, LON, as_of=NOW, rooms=2, district="arabkir")[0].listing_id) == ["b"]
    assert "c" not in set(select_cohort(f, LAT, LON, as_of=NOW, exclude_group="s")[0].listing_id)


def test_unknown_area_counts_monthly_only():
    f = df(row("a", 400, area=None), row("b", 500, area=0), row("c", 600, area=60))
    s = assess_market(f, LAT, LON, as_of=NOW)["observed_market_statistics"]
    assert s["comparables_count"] == 3 and s["area_comparables_count"] == 1
    assert s["observed_price_std_dev_per_sqm_usd"] is None
    r = assess_market(f, LAT, LON, as_of=NOW, area_sqm=50, rooms=2)
    assert r["assessment"]["status"] == "INSUFFICIENT_DATA_ABSTAIN"  # only 1 area comparable


def test_invalid_rows_dropped_and_rules_validated():
    f = df(row("a", -5), row("b", float("nan")), row("c", 100))
    assert list(select_cohort(f, LAT, LON, as_of=NOW)[0].listing_id) == ["c"]
    with pytest.raises(ValueError):
        CohortRules(window_days=61).validate()
    with pytest.raises(ValueError):
        select_cohort(KNOWN, LAT, LON, as_of=datetime(2026, 11, 1))
    with pytest.raises(ValueError):
        assess_market(KNOWN, LAT, LON, as_of=NOW, area_sqm=-1, rooms=2)


def test_inactive_listings_excluded_before_minimum_sample():
    f = df(row("a", 400), row("b", 500), row("c", 600, status="inactive"))
    r = assess_market(f, LAT, LON, as_of=NOW)
    assert r["observed_market_statistics"]["comparables_count"] == 2
    assert r["assessment"]["status"] == "INSUFFICIENT_DATA_ABSTAIN"
    assert r["assessment"]["estimated_price_usd"] is None
    assert r["cohort"]["counts"]["active"] == 2


def test_ended_at_before_as_of_is_inactive():
    f = df(row("a", 400), row("b", 500), row("c", 600), row("d", 700))
    f["ended_at"] = [None, None, "2026-10-31T00:00:00Z", "2026-11-02T00:00:00Z"]
    assert sorted(select_cohort(f, LAT, LON, as_of=NOW)[0].listing_id) == ["a", "b", "d"]


def test_status_column_required():
    with pytest.raises(ValueError, match="status"):
        select_cohort(KNOWN.drop(columns=["status"]), LAT, LON, as_of=NOW)


def test_missing_filter_columns_are_input_errors():
    with pytest.raises(ValueError, match="rooms"):
        select_cohort(KNOWN.drop(columns=["rooms"]), LAT, LON, as_of=NOW, rooms=2)
    with pytest.raises(ValueError, match="district"):
        select_cohort(KNOWN.drop(columns=["district"]), LAT, LON, as_of=NOW, district="Kentron")
    with pytest.raises(ValueError, match="rooms"):
        assess_market(KNOWN.drop(columns=["rooms"]), LAT, LON, as_of=NOW, area_sqm=50, rooms=2)
    # Unfiltered queries do not need the optional columns.
    assert assess_market(KNOWN.drop(columns=["rooms", "district"]), LAT, LON, as_of=NOW)
