import pytest
from .normalizer import normalize_price

def test_amd_daily_is_converted_to_monthly_in_both_currencies():
    r = normalize_price(10_000, "AMD", "day")
    assert r["monthly_amd"] == 300_000.0
    assert r["monthly_usd"] == 779.22

def test_amd_weekly():
    r = normalize_price(100_000, "AMD", "week")
    assert r["monthly_amd"] == pytest.approx(433_000.0)
    assert r["monthly_usd"] == pytest.approx(1124.68, abs=0.01)

def test_amd_yearly():
    r = normalize_price(4_620_000, "AMD", "year")
    assert r["monthly_amd"] == pytest.approx(385_000.0)
    assert r["monthly_usd"] == pytest.approx(1000.0)

@pytest.mark.parametrize("period", ["daily", "weekly", "yearly", "monthly", "month"])
def test_period_aliases_accepted(period):
    assert normalize_price(1000, "AMD", period)["monthly_amd"] > 0

def test_usd_monthly_amd_equivalent():
    r = normalize_price(600, "USD", "month")
    assert r["monthly_usd"] == 600.0
    assert r["monthly_amd"] == 231_000.0

def test_usd_daily_amd_matches_period():
    r = normalize_price(10, "USD", "day")
    assert r["monthly_usd"] == 300.0
    assert r["monthly_amd"] == 115_500.0

def test_unsupported_currency_and_period():
    with pytest.raises(ValueError):
        normalize_price(1, "GBP", "month")
    with pytest.raises(ValueError):
        normalize_price(1, "USD", "fortnight")

def test_utility_uncertainty_is_explicit():
    unknown = normalize_price(600, "USD", "month")
    assert unknown["utilities_included"] is None and unknown["utility_cost_uncertainty"] is True
    known = normalize_price(600, "USD", "month", includes_utilities=True)
    assert known["utilities_included"] is True and known["utility_cost_uncertainty"] is False

def test_conversion_provenance_is_returned():
    r = normalize_price(10_000, "AMD", "day")
    assert r["original_price"] == 10_000 and r["original_currency"] == "AMD"
    assert r["original_period"] == "day" and r["exchange_rate_used"] == 385.0
    assert r["conversion_timestamp"]

def test_rate_source_and_date_are_separate_from_conversion_timestamp():
    from datetime import date
    r = normalize_price(10_000, "AMD", "day")
    assert r["rate_source"] == "static-config"
    assert date.fromisoformat(r["rate_date"])                    # an effective DATE, not a timestamp
    assert "T" not in r["rate_date"] and "T" in r["conversion_timestamp"]

def test_rate_provenance_can_be_overridden(monkeypatch):
    from datetime import date
    from . import normalizer
    monkeypatch.setattr(normalizer, "EXCHANGE_RATE_SOURCE", "cba")
    monkeypatch.setattr(normalizer, "EXCHANGE_RATE_DATE", date(2026, 9, 30))
    r = normalizer.normalize_price(1, "USD", "month")
    assert (r["rate_source"], r["rate_date"]) == ("cba", "2026-09-30")