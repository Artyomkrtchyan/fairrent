import json
import re
from typing import Dict, Any, Optional
from bs4 import BeautifulSoup
import httpx

def create_listing_schema() -> Dict[str, Any]:
    return {
        "external_id": None,
        "title": "",
        "price_usd": 0.0,
        "price_amd": 0.0,
        "district": "",
        "address_raw": "",
        "area_sqm": 0.0,
        "rooms_count": 0,
        "floor": None,
        "total_floors": None,
        "building_type": "unknown",
        "description": "",
        "images": []
    }

def parse_price(price_str: str) -> tuple[float, float]:
    """Extracts numeric value and determines USD vs AMD."""
    clean_str = re.sub(r'[^\d]', '', price_str)
    val = float(clean_str) if clean_str else 0.0

    if "֏" in price_str or "AMD" in price_str:
        # Approximate exchange rate fallback or conversion placeholder
        return val / 385.0, val
    return val, val * 385.0

def parse_listing_html(html_content: str, external_id: str) -> Dict[str, Any]:
    """Parses raw HTML block from a list.am item page or card."""
    soup = BeautifulSoup(html_content, 'html.parser')
    listing = create_listing_schema()
    listing["external_id"] = external_id

    try:
        title_el = soup.find('h1', class_='pTitle') or soup.find('div', class_='header')
        if title_el:
            listing["title"] = title_el.get_text(strip=True)

        price_el = soup.find('span', class_='pPrice') or soup.find('div', class_='price')
        if price_el:
            listing["price_usd"], listing["price_amd"] = parse_price(price_el.get_text())

        # Parameters block (Rooms, Area, Floor, etc.)
        params = soup.find_all('div', class_='pattr')
        for p in params:
            text = p.get_text(strip=True)
            if any(keyword in text.lower() for keyword in ["area", "մ²", "sq", "մ"]):
                area_match = re.search(r'([\d\.]+)', text)
                if area_match:
                    listing["area_sqm"] = float(area_match.group(1))
            elif "Rooms" in text or "սենյակ" in text:
                room_match = re.search(r'(\d+)', text)
                if room_match:
                    listing["rooms_count"] = int(room_match.group(1))

        desc_el = soup.find('div', class_='pDesc')
        if desc_el:
            listing["description"] = desc_el.get_text(strip=True)

    except Exception as e:
        print(f"Parsing error for ID {external_id}: {e}")

    return listing

def fetch_or_fallback_listing(url: str, fixture_path: str = "fallback_fixture.json") -> Dict[str, Any]:
    """Fetches live listing or cleanly falls back to a local fixture if network fails."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) FairRentBot/1.0"}
    try:
        response = httpx.get(url, headers=headers, timeout=10.0)
        if response.status_code == 200:
            return parse_listing_html(response.text, external_id=url.split("/")[-1])
    except httpx.RequestError:
        print("Network request failed. Loading fallback reproducible fixture...")

    # Fallback mechanism for robust offline / sandboxed execution
    try:
        with open(fixture_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return create_listing_schema()