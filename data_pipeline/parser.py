import json
import re
from typing import Any, Dict, Optional, Tuple
import httpx
from bs4 import BeautifulSoup
from .normalizer import AMD_PER_USD, EXCHANGE_RATES

def create_listing_schema() -> Dict[str, Any]:
    return {
        "external_id": None,
        "url": None,
        "title": None,
        "price_usd": None,
        "price_amd": None,
        # Raw price as shown on the page, with its currency and period.
        "price": None,
        "currency": None,
        "period": "month",
        "lat": None,
        "lon": None,
        "district": None,
        "address_raw": None,
        "area_sqm": None,
        "rooms_count": None,
        "utilities_included": None,
        "floor": None,
        "total_floors": None,
        "building_type": None,
        "description": None,
        "images": [],
    }


def parse_price_text(price_str: str) -> Tuple[Optional[float], Optional[str], Optional[str]]:
    if not price_str:
        return None, None, None

    lowered = price_str.lower()
    if "$" in price_str or "usd" in lowered:
        currency = "USD"
    elif "€" in price_str or "eur" in lowered:
        currency = "EUR"
    else:
        currency = "AMD"

    try:
        amount = float(re.sub(r"[^\d.]", "", price_str))
    except ValueError:
        return None, None, None

    period = "day" if re.search(r"/\s*day|per day|daily|օր", lowered) else "month"
    return amount, currency, period


def parse_price(price_str: str) -> Tuple[Optional[float], Optional[float]]:
    amount, currency, _ = parse_price_text(price_str)
    if amount is None:
        return None, None
    if currency == "AMD":
        return amount / AMD_PER_USD, amount
    usd = amount / EXCHANGE_RATES[currency]
    return usd, usd * AMD_PER_USD


_LAT_RE = re.compile(r'\blat(?:itude)?\b["\']?\s*[:=]\s*["\']?(-?\d{1,2}\.\d+)', re.I)
_LON_RE = re.compile(r'\b(?:lng|lon|long|longitude)\b["\']?\s*[:=]\s*["\']?(-?\d{1,3}\.\d+)', re.I)
_MAPS_RE = re.compile(r"[?&@](?:ll=|q=)?(-?\d{1,2}\.\d{3,}),\s*(-?\d{1,3}\.\d{3,})")


def extract_coordinates(soup: BeautifulSoup, html_content: str) -> Tuple[Optional[float], Optional[float]]:
    # 1. data-lat / data-lng attributes on any element
    el = soup.find(attrs={"data-lat": True})
    if el is not None:
        lon = el.get("data-lng") or el.get("data-lon")
        try:
            return float(el["data-lat"]), float(lon)
        except (TypeError, ValueError):
            pass

    # 2. lat/lng key-value pairs in inline JSON / scripts
    lat_m, lon_m = _LAT_RE.search(html_content), _LON_RE.search(html_content)
    if lat_m and lon_m:
        return float(lat_m.group(1)), float(lon_m.group(1))

    # 3. map links such as ...?ll=40.18,44.51 or .../@40.18,44.51
    for a in soup.find_all("a", href=True):
        m = _MAPS_RE.search(a["href"])
        if m:
            return float(m.group(1)), float(m.group(2))

    return None, None


def _number(text: str):
    """int when integral, float otherwise, so '2.5 rooms' is never silently read as 2."""
    value = float(text)
    return int(value) if value == int(value) else value


def parse_listing_html(html_content: str, external_id: str) -> Dict[str, Any]:
    """Parses raw HTML block from a list.am item page or card."""
    soup = BeautifulSoup(html_content, "html.parser")
    listing = create_listing_schema()
    listing["external_id"] = external_id

    try:
        title_el = soup.find("h1", class_="pTitle") or soup.find("div", class_="header")
        if title_el:
            listing["title"] = title_el.get_text(strip=True)

        price_el = soup.find("span", class_="pPrice") or soup.find("div", class_="price")
        if price_el:
            price_text = price_el.get_text()
            listing["price_usd"], listing["price_amd"] = parse_price(price_text)
            listing["price"], listing["currency"], listing["period"] = parse_price_text(price_text)

        listing["lat"], listing["lon"] = extract_coordinates(soup, html_content)

        # Parameters block (Floor, Rooms, Area, ...). Anything not found stays None.
        for p in soup.find_all("div", class_="pattr"):
            text = p.get_text(strip=True)
            lowered = text.lower()
            if "floor" in lowered or "հարկ" in lowered:
                pair = re.search(r"(\d+)\s*/\s*(\d+)", text)
                if pair:
                    listing["floor"], listing["total_floors"] = int(pair.group(1)), int(pair.group(2))
                else:
                    single = re.search(r"(\d+(?:\.\d+)?)", text)
                    if single:
                        listing["floor"] = _number(single.group(1))
            elif "rooms" in lowered or "սենյակ" in lowered:
                room_match = re.search(r"(\d+(?:\.\d+)?)", text)
                if room_match:
                    listing["rooms_count"] = _number(room_match.group(1))
            elif any(keyword in lowered for keyword in ["area", "մ²", "sq", "մ"]):
                area_match = re.search(r"(\d+(?:\.\d+)?)", text)
                if area_match:
                    listing["area_sqm"] = float(area_match.group(1))

        desc_el = soup.find("div", class_="pDesc")
        if desc_el:
            listing["description"] = desc_el.get_text(strip=True)

    except Exception as e:
        print(f"Parsing error for ID {external_id}: {e}")

    return listing


def fetch_or_fallback_listing(url: str, fixture_path: str = "fallback_fixture.json") -> Dict[str, Any]:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) FairRentBot/1.0"}
    try:
        response = httpx.get(url, headers=headers, timeout=10.0)
        if response.status_code == 200:
            return parse_listing_html(response.text, external_id=url.split("/")[-1])
    except httpx.RequestError:
        print("Network request failed. Loading fallback reproducible fixture...")

    try:
        with open(fixture_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return create_listing_schema()