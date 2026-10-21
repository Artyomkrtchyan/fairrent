import logging
import math
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from .normalizer import EXCHANGE_RATES, monthly_multiplier
from .parser import parse_listing_html

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

USER_AGENT = "FairRentBot/1.0"
_ITEM_RE = re.compile(r"/item/(\d+)")


def _is_retryable(exc: BaseException) -> bool:
    """Retry network errors, 429 and 5xx. Do not retry 4xx such as 404."""
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status == 429 or status >= 500
    return False


def page_url(source_url: str, page: int) -> str:
    """Index URL for a 1-based page number (page 1 is the plain URL, others add ?pg=N)."""
    if page <= 1:
        return source_url
    parts = urlparse(source_url)
    query = dict(parse_qsl(parts.query))
    query["pg"] = str(page)
    return urlunparse(parts._replace(query=urlencode(query)))


def extract_listing_urls(index_html: str, base_url: str) -> List[str]:
    """Absolute, de-duplicated item URLs found on an index page, in page order."""
    soup = BeautifulSoup(index_html, "html.parser")
    urls: List[str] = []
    for a in soup.find_all("a", href=_ITEM_RE):
        url = urljoin(base_url, a["href"])
        if url not in urls:
            urls.append(url)
    return urls


_BLOCK_RE = re.compile(
    r"captcha|access denied|forbidden|are you (?:a )?(?:human|robot)|unusual traffic|"
    r"verify (?:that )?you are|just a moment|attention required|too many requests|rate limit",
    re.I,
)


def catalogue_signature(index_html: str) -> Optional[tuple]:
    """Structural fingerprint of a genuine catalogue page: (tag, id, classes) of the nearest
    identifiable element wrapping the listing links. Taken from a page that DID contain listings."""
    soup = BeautifulSoup(index_html, "html.parser")
    link = soup.find("a", href=_ITEM_RE)
    if link is None:
        return None
    for parent in link.parents:
        if parent.name in (None, "[document]", "html", "body"):
            break
        classes = tuple(sorted(parent.get("class") or []))
        if parent.get("id") or classes:
            return (parent.name, parent.get("id"), classes)
    return None


def has_catalogue_structure(index_html: str, signature: Optional[tuple]) -> bool:
    if signature is None:
        return False
    tag, elem_id, classes = signature
    soup = BeautifulSoup(index_html, "html.parser")
    return any(
        el.get("id") == elem_id and tuple(sorted(el.get("class") or [])) == classes
        for el in soup.find_all(tag)
    )


def looks_blocked(index_html: str) -> bool:
    """CAPTCHA / 'Access denied' style pages (only consulted when a page has no listings)."""
    soup = BeautifulSoup(index_html, "html.parser")
    text = " ".join(filter(None, [soup.title.get_text(" ") if soup.title else "",
                                  soup.get_text(" ", strip=True)[:2000]]))
    return bool(_BLOCK_RE.search(text))


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _to_number(value: Any, field: str) -> float:
    """Converts int/float/numeric-string to a finite float, otherwise raises ValueError."""
    if value is None or isinstance(value, bool):
        raise ValueError(f"{field} is missing or not numeric")
    if isinstance(value, str):
        value = value.strip().replace(",", "")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be numeric, got {value!r}")
    if not math.isfinite(number):
        raise ValueError(f"{field} must be a finite number, got {value!r}")
    return number


def _clean_text(value: Any) -> Optional[str]:
    """Empty strings and the legacy 'unknown' sentinel become None (= unknown)."""
    if value is None:
        return None
    text = str(value).strip()
    return None if text == "" or text.lower() == "unknown" else text


def _optional_number(value: Any, minimum: float, integer: bool = False) -> Optional[float]:
    """Optional numeric attribute. Missing, unparsable or below `minimum` -> None (unknown).
    A legitimate 0 is kept when minimum <= 0."""
    try:
        number = _to_number(value, "optional field")
    except ValueError:
        return None
    if number < minimum:
        return None
    if integer:
        if number != int(number):      # 2.9 rooms is not "2 rooms": unknown, not truncated
            return None
        return int(number)
    return number


class ListingPipeline:
    def __init__(self, client: Optional[httpx.Client] = None, delay: float = 1.0):
        self.quarantine_log: List[dict] = []
        self.delay = delay
        self._owns_client = client is None
        self._client = client or httpx.Client(
            headers={"User-Agent": USER_AGENT}, timeout=10.0, follow_redirects=True
        )
        self._requests_made = 0
        self.reset_crawl_state()

    def reset_crawl_state(self) -> None:
        self.seen_ids: set = set()        # external ids observed on index pages
        self.pages_requested = 0
        self.pages_fetched = 0
        self.index_failures = 0
        self.detail_failures = 0
        self.reached_end = False          # an index page past page 1 had no listings
        self.capped = False               # stopped early because of --max-listings
        self.finished = False             # generator ran to a normal end
        self.catalogue_signature = None   # structure of page 1; later pages must look the same

    @property
    def crawl_complete(self) -> bool:
        """True only if the whole segment was observed: pagination reached its end, no index
        page failed and no early stop happened. Only such a crawl may deactivate listings."""
        return self.finished and self.reached_end and self.index_failures == 0 and not self.capped

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    # ---- collection -------------------------------------------------------

    @retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def fetch_page(self, url: str) -> str:
        """Fetches a page with bounded retries for transient network/server errors."""
        if self._requests_made and self.delay > 0:
            time.sleep(self.delay)  # be polite to the source site
        self._requests_made += 1
        response = self._client.get(url)
        response.raise_for_status()
        return response.text

    def collect(self, source_url: str, pages: int, max_listings: Optional[int] = None) -> Iterator[Dict[str, Any]]:
        """Walks up to `pages` index pages, fetches each listing page, parses it and yields raw items.
        Crawl state (seen_ids, reached_end, failures) is kept on the pipeline for run summaries."""
        self.reset_crawl_state()
        self.pages_requested = pages
        seen_urls = set()
        yielded = 0
        for page in range(1, pages + 1):
            index_url = page_url(source_url, page)
            try:
                index_html = self.fetch_page(index_url)
            except httpx.HTTPError as e:
                self.index_failures += 1
                self.quarantine({"url": index_url}, f"Failed to fetch index page {page}: {e}")
                continue
            self.pages_fetched += 1

            item_urls = extract_listing_urls(index_html, index_url)
            if item_urls and page == 1:
                self.catalogue_signature = catalogue_signature(index_html)
            if not item_urls:
                if page == 1:
                    # An empty first page is more likely a block/markup change than an empty market.
                    self.index_failures += 1
                    logger.warning("First index page has no listings; treating the crawl as incomplete.")
                elif (not looks_blocked(index_html)
                      and has_catalogue_structure(index_html, self.catalogue_signature)):
                    self.reached_end = True
                    logger.info("No listings on page %d; end of pagination.", page)
                else:
                    # CAPTCHA / access denied / changed markup: NOT evidence that the catalogue ended.
                    self.index_failures += 1
                    self.quarantine({"url": index_url},
                                    f"Index page {page} is not a recognizable catalogue page "
                                    "(blocked, CAPTCHA or changed markup); not treated as end of pagination")
                break

            for url in item_urls:
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                external_id = _ITEM_RE.search(url).group(1)
                self.seen_ids.add(external_id)       # seen on the source, even if the detail fetch fails
                if max_listings is not None and yielded >= max_listings:
                    self.capped = True
                    return
                try:
                    item_html = self.fetch_page(url)
                except httpx.HTTPError as e:
                    self.detail_failures += 1
                    self.quarantine({"url": url}, f"Failed to fetch listing: {e}")
                    continue

                parsed = parse_listing_html(item_html, external_id=external_id)
                yield {**parsed, "id": external_id, "url": url}
                yielded += 1
        self.finished = True

    # ---- validation -------------------------------------------------------

    def quarantine(self, raw_data: dict, reason: str) -> None:
        self.quarantine_log.append({
            "raw_data": raw_data,
            "error": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        logger.warning("Quarantined record due to: %s", reason)

    def parse_and_validate_record(self, raw_item: dict) -> Optional[dict]:
        try:
            item_id = raw_item.get("id")
            if item_id is None or not str(item_id).strip():
                raise ValueError("Missing id")

            price = _to_number(raw_item.get("price"), "price")
            if price <= 0:
                raise ValueError("Price must be greater than zero")

            # Coordinates: both missing is allowed (listing stays searchable, just not on the map);
            # exactly one missing, non-numeric or out-of-range is invalid.
            lat_blank, lon_blank = _is_blank(raw_item.get("lat")), _is_blank(raw_item.get("lon"))
            if lat_blank != lon_blank:
                raise ValueError("latitude and longitude must both be present or both be missing")
            lat = lon = None
            if not lat_blank:
                lat = _to_number(raw_item.get("lat"), "latitude")
                lon = _to_number(raw_item.get("lon"), "longitude")
                if not -90 <= lat <= 90:
                    raise ValueError(f"Latitude out of range [-90, 90]: {lat}")
                if not -180 <= lon <= 180:
                    raise ValueError(f"Longitude out of range [-180, 180]: {lon}")

            currency = str(raw_item.get("currency") or "").upper()
            if currency not in EXCHANGE_RATES:
                raise ValueError(f"Unsupported currency: {currency or 'missing'}")
            period = raw_item.get("period") or "month"
            monthly_multiplier(period)  # raises ValueError for unknown periods

            area = _optional_number(raw_item.get("area_sqm"), minimum=1)
            rooms = _optional_number(raw_item.get("rooms_count"), minimum=1, integer=True)
            floor = _optional_number(raw_item.get("floor"), minimum=0, integer=True)
            total_floors = _optional_number(raw_item.get("total_floors"), minimum=1, integer=True)
            if floor is not None and total_floors is not None and floor > total_floors:
                floor = total_floors = None  # contradictory -> unknown rather than wrong
            checked = {"area_sqm": area, "rooms_count": rooms, "floor": floor, "total_floors": total_floors}
            # Values the source supplied but we refused (non-integral rooms, contradictions, ...):
            rejected = {k: raw_item.get(k) for k, v in checked.items()
                        if v is None and not _is_blank(raw_item.get(k))}

            cleaned = {
                **raw_item,
                "id": str(item_id).strip(),
                "price": price,
                "lat": lat,
                "lon": lon,
                "currency": currency,
                "period": period,
                "title": _clean_text(raw_item.get("title")),
                "district": _clean_text(raw_item.get("district")),
                "address_raw": _clean_text(raw_item.get("address_raw")),
                "building_type": _clean_text(raw_item.get("building_type")),
                "description": _clean_text(raw_item.get("description")),
                "area_sqm": area,
                "rooms_count": rooms,
                "floor": floor,
                "total_floors": total_floors,
            }
            # Explicit list so the API/analysts can tell "unknown" from a real value.
            cleaned["missing_fields"] = sorted(
                [k for k in ("area_sqm", "rooms_count", "floor", "total_floors", "building_type",
                             "district", "address_raw", "description", "title")
                 if cleaned.get(k) is None]
                + (["coordinates"] if lat is None else [])
            )
            cleaned["rejected_fields"] = rejected   # {field: original value} for traceability
            return cleaned
        except ValueError as e:
            self.quarantine(raw_item, str(e))
            return None