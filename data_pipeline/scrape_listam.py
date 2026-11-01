"""
Weekly list.am apartment-rental scraper -> JSON (with coordinates).

Install:
    pip install cloakbrowser beautifulsoup4

Usage:
    python scrape_listam.py                         # listing pages + fill missing coordinates from ad pages
    python scrape_listam.py --max-pages 2 --details-limit 5   # quick test run
    python scrape_listam.py --yerevan-only          # Yerevan districts only (faster)
    python scrape_listam.py --no-coords             # listing pages only, do not open individual ads
    python scrape_listam.py --details               # open ALL ads (also fills utilities_included)
    python scrape_listam.py --resume listings_2026-10-29.json   # continue an existing file

You can stop with Ctrl+C at any time: progress is saved, and --resume continues from there.

How it works:
  Stage 1 - listing pages. /category/56, /category/56/2, /category/56/3, ... are downloaded
            one by one. Each page gives cards (id, title, price, rooms/area/floor, district)
            and an inline script map_snapshot.init(...) with map points {lat, lng, ids:[...]}.
            Coordinates for many ads come from there. USD prices are converted to AMD using
            the rate list.am itself embeds in that script.
  Stage 2 - ad pages. For every ad that still has no coordinates (or for all ads with
            --details), the ad page is opened and the map position is read from it.
            utilities_included only exists on ad pages.

Be polite to the site: there are pauses between requests and requests run strictly one at a time.
"""
import argparse
import json
import random
import re
import statistics
import time
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup

# ============================================================== SETTINGS
# What to scrape. Change these to scrape something else.
BASE = "https://www.list.am"
CATEGORY = "/category/56"      # long-term apartment rentals (all of Armenia, no location filter)
DEFAULT_MAX_PAGES = 50         # upper limit of listing pages (stops earlier if a page has nothing new)
DEFAULT_DELAY = 3.0            # minimum pause between requests, seconds (+0..3 s random)
SAVE_EVERY = 20                # save the JSON after every N ad pages
# ==========================================================================

CF_MARKERS = ("just a moment", "attention required", "checking your browser")

# Armenian text used on the site -> English name. The Armenian keys must stay Armenian,
# because that is exactly what list.am shows on its pages.
DISTRICTS = {
    "Կենտրոն": "Kentron",
    "Արաբկիր": "Arabkir",
    "Աջափնյակ": "Ajapnyak",
    "Ավան": "Avan",
    "Դավթաշեն": "Davtashen",
    "Էրեբունի": "Erebuni",
    "Քանաքեռ-Զեյթուն": "Kanaker-Zeytun",
    "Մալաթիա-Սեբաստիա": "Malatia-Sebastia",
    "Նոր Նորք": "Nor Nork",
    "Նորք-Մարաշ": "Nork-Marash",
    "Նուբարաշեն": "Nubarashen",
    "Շենգավիթ": "Shengavit",
    "Վահագնի թաղամաս": "Vahagni",
    # not Yerevan districts
    "Գյումրի": "Gyumri",
    "Վանաձոր": "Vanadzor",
    "Գառնի": "Garni",
    "Դիլիջան": "Dilijan",
    "Սևան": "Sevan",
    "Առինջ": "Arinj",
    "Ծաղկաձոր": "Tsaghkadzor",
    "Աբովյան": "Abovyan",
    "Հրազդան": "Hrazdan",
    "Քասախ": "Kasakh",
    "Բյուրեղավան": "Byureghavan",
}
NOT_YEREVAN = {"Gyumri", "Vanadzor", "Garni", "Dilijan", "Sevan", "Arinj",
               "Tsaghkadzor", "Abovyan", "Hrazdan", "Kasakh", "Byureghavan"}

CURRENCIES = {"֏": "AMD", "$": "USD", "€": "EUR", "₽": "RUB"}
PERIODS = {"ամսական": "month", "օրական": "day"}


# ---------------------------------------------------------------- parsing

def to_int(s):
    digits = re.sub(r"[^\d]", "", s or "")
    return int(digits) if digits else None


def to_num(s):
    s = s.replace(",", ".")
    v = float(s)
    return int(v) if v.is_integer() else v


def extract_map_points(html):
    """Read the inline map_snapshot.init(...) script.
    Returns ({ad_id: (lat, lon)}, [USD->AMD rates])."""
    i = html.find("map_snapshot.init(")
    if i < 0:
        return {}, []
    j = html.find("{", i)
    try:
        data, _ = json.JSONDecoder().raw_decode(html[j:])
    except ValueError:
        return {}, []
    coords, rates = {}, []
    for p in data.get("data", []):
        try:
            lat, lon = float(p["lat"]), float(p["lng"])
        except (KeyError, ValueError, TypeError):
            continue
        for _id in p.get("ids", []):
            coords[str(_id)] = (lat, lon)
        # single-ad points labelled in USD reveal the exchange rate list.am uses
        label = p.get("label", "")
        if p.get("count") == 1 and label.startswith("$") and p.get("sortPrice"):
            usd = to_int(label)
            if usd:
                rates.append(p["sortPrice"] / usd)
    return coords, rates


def parse_cards(html):
    """Extract ad cards from a listing page."""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for card in soup.select(".category-data-list-grid-card"):
        a = card.select_one("a[href*='/item/']")
        if not a:
            continue
        m = re.search(r"/item/(\d+)", a["href"])
        if not m:
            continue

        title_el = a.select_one(".l")
        title = title_el.get_text(" ", strip=True) if title_el else None

        price = currency = period = None
        amount = a.select_one(".category-data-list-card__amount")
        if amount:
            cur_el = amount.select_one(".category-data-list-card__currency")
            currency = CURRENCIES.get(cur_el.get_text(strip=True)) if cur_el else None
            price = to_int(amount.get_text())
        freq = a.select_one(".category-data-list-card__price-frequency")
        if freq:
            period = PERIODS.get(freq.get_text(strip=True))

        # line like "3 rooms, 125 sqm, 12/17 floor" - a direct child of the link (not the location)
        at_el = a.find("div", class_="at", recursive=False)
        at = at_el.get_text(" ", strip=True) if at_el else ""
        src = at + " | " + (title or "")

        rooms = area = floor = total = None
        mm = re.search(r"(\d+)\s*սեն", at) or re.search(r"(\d+)\s*սենյականոց", title or "")
        if mm:
            rooms = int(mm.group(1))
        mm = re.search(r"(\d+(?:[.,]\d+)?)\s*քմ", src)
        if mm:
            area = to_num(mm.group(1))
        mm = re.search(r"(\d+)\s*/\s*(\d+)\s*հարկ", src)
        if mm:
            floor, total = int(mm.group(1)), int(mm.group(2))

        loc_el = a.select_one(".category-data-list-card__location")
        loc = loc_el.get_text(strip=True) if loc_el else None

        out.append({
            "id": m.group(1), "title": title, "price": price, "currency": currency,
            "period": period, "rooms": rooms, "area": area, "floor": floor,
            "total_floors": total, "district_raw": loc,
        })
    return out


def parse_detail(html):
    """From an ad page: utilities_included (True/False/None) and map coordinates."""
    soup = BeautifulSoup(html, "html.parser")
    utilities = None
    for block in soup.select(".attr"):
        texts = [p.get_text(" ", strip=True) for p in block.select("p")]
        if "Կոմունալ վճարումներ" in texts:      # "Utility payments"
            if "Չներառված" in texts:            # "Not included"
                utilities = False
            elif "Ներառված" in texts:           # "Included"
                utilities = True
            break
    lat = lon = None
    m = re.search(r'init\("poiMap",\s*(-?\d+\.\d+),\s*(-?\d+\.\d+)', html)
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
    return {"utilities_included": utilities, "lat": lat, "lon": lon}


def build_record(card, coords, usd_rate):
    """Turn a raw card into the final JSON record."""
    price, currency = card["price"], card["currency"]
    price_original, currency_original = price, currency
    if currency == "USD" and price is not None and usd_rate:
        price, currency = round(price * usd_rate), "AMD"

    district = DISTRICTS.get(card["district_raw"], card["district_raw"])
    ll = coords.get(card["id"])
    return {
        "external_id": card["id"],
        "title": card["title"],
        "price": price,
        "currency": currency,
        "period": card["period"],
        "lat": ll[0] if ll else None,
        "lon": ll[1] if ll else None,
        "area_sqm": card["area"],
        "rooms_count": card["rooms"],
        "floor": card["floor"],
        "total_floors": card["total_floors"],
        "district": district,
        "url": f"{BASE}/item/{card['id']}",
        "utilities_included": None,
        "coordinate_source": "list.am:inline-script-array" if ll else None,
        "coordinate_confidence": "approximate" if ll else None,
        "district_source": "list.am:card-location" if district else None,
        "price_original": price_original,
        "currency_original": currency_original,
    }


def is_yerevan(rec):
    d = rec["district"]
    return bool(d) and d not in NOT_YEREVAN and d in DISTRICTS.values()


def save(path, records):
    """Write to a temp file first, then replace, so the JSON is never half-written."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------- browser

def is_challenge(page):
    # check the title only: Cloudflare's challenge-platform script also exists on normal pages
    return any(m in (page.title() or "").lower() for m in CF_MARKERS)


def wait_past_challenge(page, seconds=30):
    for _ in range(seconds // 2):
        if not is_challenge(page):
            return True
        time.sleep(2)  # time.sleep, not page.wait_for_timeout
    return not is_challenge(page)


def make_fetcher(page):
    def fetch(url):
        for attempt in range(2):
            resp = page.goto(url)
            status = resp.status if resp else 0
            if status in (403, 429, 503) or not wait_past_challenge(page):
                print(f"    ! {url}: status {status}, waiting and retrying...")
                time.sleep(15 * (attempt + 1))
                continue
            return page.content()
        raise RuntimeError(f"Could not load {url} (Cloudflare/blocked)")
    return fetch


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES,
                    help="max number of listing pages to scrape")
    ap.add_argument("--delay", type=float, default=DEFAULT_DELAY,
                    help="minimum pause between requests, seconds")
    ap.add_argument("--no-coords", action="store_true",
                    help="do not open ad pages to fill missing coordinates")
    ap.add_argument("--details", action="store_true",
                    help="open ALL ad pages (also fills utilities_included)")
    ap.add_argument("--details-limit", type=int, default=None,
                    help="max number of ad pages to open")
    ap.add_argument("--yerevan-only", action="store_true",
                    help="keep only Yerevan districts")
    ap.add_argument("--resume", default=None,
                    help="existing JSON file: skip listing pages, continue filling")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--proxy", default=None)
    ap.add_argument("--out", default=None, help="output file name")
    args = ap.parse_args()

    # imported here so the parsers can be tested without a browser
    from cloakbrowser import launch_persistent_context

    out = Path(args.resume or args.out or f"listings_{date.today().isoformat()}.json")

    kwargs = dict(headless=args.headless, humanize=True)
    if args.proxy:
        kwargs.update(proxy=args.proxy, geoip=True)
    ctx = launch_persistent_context("./profile", **kwargs)
    page = ctx.new_page()
    fetch = make_fetcher(page)

    def pause():
        time.sleep(random.uniform(args.delay, args.delay + 3))

    records = []
    try:
        # ---------- stage 1: listing pages
        if args.resume:
            records = json.loads(out.read_text(encoding="utf-8"))
            print(f"Resuming from {out}: {len(records)} listings")
        else:
            cards, coords, rates = {}, {}, []
            for n in range(1, args.max_pages + 1):
                url = BASE + CATEGORY + ("" if n == 1 else f"/{n}")
                html = fetch(url)
                page_cards = parse_cards(html)
                c, r = extract_map_points(html)
                coords.update(c)
                rates.extend(r)
                new = [x for x in page_cards if x["id"] not in cards]
                for x in new:
                    cards[x["id"]] = x
                print(f"[page {n}] cards: {len(page_cards)}, new: {len(new)}, total: {len(cards)}")
                if not new:  # nothing new -> we are past the last page
                    break
                pause()

            usd_rate = statistics.median(rates) if rates else None
            print(f"USD->AMD rate from list.am: {usd_rate}; points with coordinates: {len(coords)}")
            records = [build_record(c, coords, usd_rate) for c in cards.values()]
            if args.yerevan_only:
                records = [r for r in records if is_yerevan(r)]
                print(f"After --yerevan-only filter: {len(records)}")
            save(out, records)  # listing results are saved even if stage 2 is interrupted
            print(f"Listing results saved to {out}")

        # ---------- stage 2: open ad pages
        def needs_visit(r):
            if r.get("detail_checked"):
                return False
            if args.yerevan_only and not is_yerevan(r):
                return False
            return (r["lat"] is None and not args.no_coords) or args.details

        todo = [r for r in records if needs_visit(r)]
        if args.details_limit:
            todo = todo[: args.details_limit]
        if todo:
            print(f"\nAd pages to open: {len(todo)} (~{len(todo) * 7 // 60} min)")

        for k, rec in enumerate(todo, 1):
            try:
                d = parse_detail(fetch(rec["url"]))
            except Exception as e:  # noqa: BLE001
                print(f"    ! {rec['url']}: {e}")
                continue
            rec["detail_checked"] = True
            if rec["utilities_included"] is None:
                rec["utilities_included"] = d["utilities_included"]
            if rec["lat"] is None and d["lat"] is not None:
                rec["lat"], rec["lon"] = d["lat"], d["lon"]
                rec["coordinate_source"] = "list.am:detail-page-map"
                rec["coordinate_confidence"] = "approximate"
            print(f"[{k}/{len(todo)}] {rec['external_id']} coords={'yes' if rec['lat'] is not None else 'no'}")
            if k % SAVE_EVERY == 0:
                save(out, records)
            pause()
    finally:
        if records:
            save(out, records)
        ctx.close()

    no_coords = sum(r["lat"] is None for r in records)
    unmapped = {r["district"] for r in records if r["district"] and r["district"] not in DISTRICTS.values()}
    print(f"\nDone: {len(records)} listings -> {out}")
    print(f"Without coordinates: {no_coords}")
    if unmapped:
        print(f"Districts missing from DISTRICTS: {unmapped}")


if __name__ == "__main__":
    main()