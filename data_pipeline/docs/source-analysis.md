# Source analysis: list.am Yerevan long-term rentals [A01]

Scope: the rental-apartments segment configured by `--source-url` (default `https://www.list.am/category/56`).

> **Verification status.** The parser selectors, the paging parameter and the update behaviour below are
> *implemented assumptions* that have been exercised only against project-owned mock pages
> (`test_scraper.py`, `test_parser.py`), never against the live site (README: tests target
> project-owned environments). Rows marked **VERIFY** must be checked once, by hand, against a real page
> before the first production run, and this document updated.

## 1. Field mapping (source -> shared data contract)

| Contract field (table.column) | Source element / rule | Missing-value behaviour | Status |
|---|---|---|---|
| `listings.external_id` | numeric id from `/item/<id>` in the URL | record rejected (quarantine) | implemented |
| `listings.url` | listing page URL | stored as NULL if unknown | implemented |
| `listings.title` | `h1.pTitle` / `div.header` | NULL | VERIFY selector |
| price (`original_price`, `original_currency`, `original_period`) | `span.pPrice` / `div.price`: `$`/USD, `€`/EUR, otherwise AMD; period `day` if text says `/day`, `daily`, `օր`, else `month` | record rejected (quarantine) | VERIFY selector, period wording |
| `listings.price_usd`, `price_amd` | derived: monthly amounts from original price (see normalizer) | not stored if price invalid | implemented |
| `properties.geom` (lat/lon) | `data-lat`/`data-lng` attributes, inline `lat`/`lng` pairs, or map links `?ll=lat,lon` | both missing: listing is **kept** with `Property.geom = NULL` (searchable, excluded from map results); only one present, non-numeric or out of range: record rejected | **VERIFY** (most likely to need adjusting) |
| `listings.area_sqm` | `div.pattr` containing area/`sq`/`մ²` | NULL (never 0) | VERIFY selector |
| `listings.rooms_count` | `div.pattr` containing `rooms`/`սենյակ` | NULL (never 0) | VERIFY selector |
| `listings.floor`, `total_floors` | `div.pattr` containing `floor`/`հարկ`, `5/9` or `5` | NULL; `floor > total_floors` -> both NULL | VERIFY selector |
| `listings.description` | `div.pDesc` | NULL | VERIFY selector |
| `listings.building_type`, `properties.district`, `properties.address_raw` | not extracted yet | NULL | follow-up |
| `listings.utilities_included` | not stated reliably by the source | NULL = unknown (`utility_cost_uncertainty = true`) | by design |

Missing values: optional attributes are `NULL` when unknown. A real `0` is kept only where it is meaningful
(ground floor `floor = 0`). Each stored record carries `raw_data.missing_fields` listing what was unknown.

## 2. Pagination

* Index pages: `<source-url>` for page 1 and `<source-url>?pg=N` for N > 1 (**VERIFY** parameter name).
* Item links are found with `a[href*="/item/<digits>"]` and de-duplicated across pages.
* End of pagination = an index page after page 1 with no item links **that is also recognisable as a genuine
  catalogue page**: it must contain the same wrapper element (tag/id/classes) that held the listing links on page 1
  and must not look like a CAPTCHA / "Access denied" page. Anything else (blocked, CAPTCHA, maintenance page,
  changed markup, or a page 1 without a distinctive wrapper, which makes the end unverifiable) counts as an index
  failure: the run becomes **partial** and cannot deactivate listings. An **empty first page** is also a failure.
  **VERIFY** what the real end-of-catalogue page looks like; if it is not an empty catalogue wrapper (e.g. a redirect),
  runs will stay partial until the rule is adapted. That is the safe direction.
* `--pages N` is a safety cap. A run that stops at the cap, at `--max-listings`, or after any failed index page
  is recorded as **partial** and can never deactivate listings.

## 3. Source update behaviour

What the pipeline does not assume: that the site tells us when a listing changed or was removed. Instead:

* Every run re-observes the index; a listing present on the index is "seen" (even if its detail page failed).
* Changes are detected on our side: a new `price_observations` row is written when the original price,
  currency, period or the normalized USD/AMD amounts differ from the latest observation.
* Disappearance is inferred only from complete runs under the staleness policy
  (`docs/storage-and-ingestion.md`).
* **VERIFY** and document: whether edited ads keep the same id, whether renewed/"bumped" ads change position
  or id, and how long removed ads stay reachable (404/410 vs. "archived" page).

## 4. Collection constraints and rate limits

| Constraint | Value / behaviour |
|---|---|
| Request rate | one request per `--delay` seconds (default 1.0) |
| Retries | at most 3 attempts, exponential backoff 2-10 s; only network errors, HTTP 429 and 5xx are retried, 4xx (e.g. 404) are not |
| Timeout | 10 s per request |
| User agent | `FairRentBot/1.0` (identifiable; no browser impersonation) |
| Failure handling | failed or unrecognised/blocked index page -> run partial; failed detail page -> record quarantined, listing still counts as seen |
| Testing | only project-owned mock servers / local fixtures; never the live site |
| Compliance | **VERIFY** the site's robots.txt and terms for automated access before scheduling weekly runs |

## 5. Reproducible fallback import (access fails)

```bash
# synthetic, committed to the repo: data_pipeline/fallback_fixture.json, data_pipeline/seed_data.json
python -m data_pipeline.cli import-file data_pipeline/fallback_fixture.json --source-name fixture
python -m data_pipeline.cli import-file data_pipeline/seed_data.json --source-name synthetic
```

`import-file` uses the same validation, normalization and loading as a crawl, records an `ingestion_runs`
row, is idempotent, and never deactivates anything. Both files contain synthetic data only
(ids `SYN-*` / `S-*`, `example.invalid` URLs). Do not commit real raw exports (README).
