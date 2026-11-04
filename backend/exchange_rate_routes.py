"""Live CBA USD/AMD quote exposed through the existing C01 ExchangeRate contract.

The provider is the Central Bank of Armenia SOAP service. Never use the
synthetic frontend rate or invent a rate when the upstream is unavailable.
"""
import math
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v1/exchange-rate", tags=["exchange-rate"])

CBA_URL = "https://api.cba.am/exchangerates.asmx"
CBA_NS = "{http://www.cba.am/}"
MAX_AGE_DAYS = 7
CACHE_SECONDS = 900
_CBA_SOAP = b'''<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body><ExchangeRatesLatestByISO xmlns="http://www.cba.am/">
    <ISO>USD</ISO>
  </ExchangeRatesLatestByISO></soap:Body>
</soap:Envelope>'''
_cache_lock = threading.Lock()
_cache = None


def _utc(value):
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _fetch_rate():
    request = urllib.request.Request(
        CBA_URL,
        data=_CBA_SOAP,
        headers={
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": '"http://www.cba.am/ExchangeRatesLatestByISO"',
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=4) as response:
        if response.status != 200:
            raise ValueError("Unexpected CBA response status")
        body = response.read(65537)
    if len(body) > 65536 or b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():
        raise ValueError("Invalid CBA response")
    root = ET.fromstring(body)
    result = root.find(".//" + CBA_NS + "ExchangeRatesLatestByISOResult")
    if result is None:
        raise ValueError("Missing CBA rate result")
    published = result.findtext(CBA_NS + "CurrentDate")
    if not published:
        raise ValueError("Missing CBA publication date")
    observed = datetime.fromisoformat(published.replace("Z", "+00:00"))
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=ZoneInfo("Asia/Yerevan"))
    observed = observed.astimezone(timezone.utc)
    for entry in result.findall(".//" + CBA_NS + "ExchangeRate"):
        if entry.findtext(CBA_NS + "ISO") != "USD":
            continue
        amount = float(entry.findtext(CBA_NS + "Amount") or "nan")
        rate = float(entry.findtext(CBA_NS + "Rate") or "nan")
        if not all(math.isfinite(n) and n > 0 for n in (amount, rate)):
            break
        return rate / amount, observed
    raise ValueError("CBA response has no usable USD quote")


def _latest_rate():
    global _cache
    now = time.monotonic()
    with _cache_lock:
        if _cache is not None and now - _cache[0] < CACHE_SECONDS:
            return _cache[1], _cache[2]
        try:
            rate, observed = _fetch_rate()
        except (OSError, ValueError, ET.ParseError, TimeoutError):
            # A previously fetched rate retains its original observation time.
            if _cache is not None:
                return _cache[1], _cache[2]
            raise
        _cache = (time.monotonic(), rate, observed)
        return rate, observed


def _response(rate, observed, now):
    stale = observed > now + timedelta(days=1) or now - observed > timedelta(days=MAX_AGE_DAYS)
    return {
        "base_currency": "USD",
        "quote_currency": "AMD",
        "amd_per_usd": rate,
        "source": "Central Bank of Armenia",
        "effective_at": _utc(observed),
        "status": "stale" if stale else "available",
        "freshness": {
            "data_as_of": _utc(observed),
            "generated_at": _utc(now),
            "is_stale": stale,
            "max_age_days": MAX_AGE_DAYS,
            "policy_version": "fx-proposal-v1",
        },
    }


@router.get("")
def exchange_rate():
    try:
        rate, observed = _latest_rate()
    except (OSError, ValueError, ET.ParseError, TimeoutError):
        raise HTTPException(status_code=503, detail="Exchange rate provider unavailable") from None
    return _response(rate, observed, datetime.now(timezone.utc))
