import os
from datetime import date, datetime, timezone

# Approximate exchange rates (units of currency per 1 USD).
AMD_PER_USD = 385.0
EXCHANGE_RATES = {
    "USD": 1.0,
    "AMD": AMD_PER_USD,
    "EUR": 0.92,
}
EXCHANGE_RATE_SOURCE = os.environ.get("EXCHANGE_RATE_SOURCE", "static-config")
EXCHANGE_RATE_DATE = date.fromisoformat(os.environ.get("EXCHANGE_RATE_DATE", "2026-10-21"))

DAYS_PER_MONTH = 30
WEEKS_PER_MONTH = 4.33


def monthly_multiplier(period: str | None) -> float:
    """Factor that converts a price quoted per `period` into a per-month price."""
    p = (period or "month").strip().lower()
    if "day" in p or "daily" in p:
        return DAYS_PER_MONTH
    if "week" in p:
        return WEEKS_PER_MONTH
    if "year" in p or "annual" in p:
        return 1 / 12
    if "month" in p:
        return 1.0
    raise ValueError(f"Unsupported rental period: {period!r}")


def normalize_price(raw_price: float, currency: str, period: str,
                    includes_utilities: bool | None = None) -> dict:
    curr = (currency or "").upper()
    if curr not in EXCHANGE_RATES:
        raise ValueError(f"Unsupported currency: {curr}")

    multiplier = monthly_multiplier(period)

    monthly_original = raw_price * multiplier            # in the original currency
    monthly_usd = monthly_original / EXCHANGE_RATES[curr]
    monthly_amd = monthly_original if curr == "AMD" else monthly_usd * AMD_PER_USD

    return {
        "monthly_usd": round(monthly_usd, 2),
        "monthly_amd": round(monthly_amd, 2),
        "original_price": raw_price,
        "original_currency": curr,
        "original_period": period,
        "period_multiplier": multiplier,
        "exchange_rate_used": EXCHANGE_RATES[curr],
        "rate_source": EXCHANGE_RATE_SOURCE,
        "rate_date": EXCHANGE_RATE_DATE.isoformat(),          # effective date of the rate
        "conversion_timestamp": datetime.now(timezone.utc).isoformat(),   # when we converted
        "utilities_included": includes_utilities,
        # True when we do not know whether utilities are part of the price.
        "utility_cost_uncertainty": includes_utilities is None,
    }