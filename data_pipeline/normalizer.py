from datetime import datetime

def normalize_price(raw_price: float, currency: str, period: str, includes_utilities: bool = False) -> dict:
    """
    Normalizes rental prices to monthly USD amounts.
    Preserves original currency, conversion provenance, and utility uncertainties.
    """
    # Approximate exchange rates 
    exchange_rates = {
        "USD": 1.0,
        "AMD": 385.0,  # Example AMD to USD rate
        "EUR": 0.92    # Example EUR to USD rate
    }
    
    curr = currency.upper()
    if curr not in exchange_rates:
        raise ValueError(f"Unsupported currency: {curr}")
        
    # Convert to USD base
    price_in_usd = raw_price / exchange_rates[curr]
    
    # Normalize period to monthly
    p = period.lower()
    if "day" in p or "daily" in p:
        monthly_usd = price_in_usd * 30
    elif "week" in p or "weekly" in p:
        monthly_usd = price_in_usd * 4.33
    elif "year" in p or "yearly" in p:
        monthly_usd = price_in_usd / 12
    else:  # Assumed monthly
        monthly_usd = price_in_usd
        
    return {
        "monthly_usd": round(monthly_usd, 2),
        "original_price": raw_price,
        "original_currency": curr,
        "exchange_rate_used": exchange_rates[curr],
        "conversion_timestamp": datetime.utcnow().isoformat(),
        "utility_cost_uncertainty": includes_utilities
    }