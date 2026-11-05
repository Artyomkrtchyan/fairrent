"""Backfill photo URLs for existing List.am listings using PostgreSQL PG* settings."""

import argparse
import math
import re
import sys
import time
from contextlib import contextmanager

import httpx
import psycopg
from bs4 import BeautifulSoup

from .parser import extract_images
from .scraper import USER_AGENT, looks_blocked

MISSING_IMAGES = """
    CASE WHEN jsonb_typeof(raw_data::jsonb -> 'images') = 'array'
         THEN jsonb_array_length(raw_data::jsonb -> 'images') = 0
         ELSE true END
"""


@contextmanager
def open_detail_pages(browser):
    if browser:
        from playwright.sync_api import Error, sync_playwright

        with sync_playwright() as playwright:
            chromium = playwright.chromium.launch()
            try:
                page = chromium.new_page()

                def fetch(url):
                    response = page.goto(url, wait_until="domcontentloaded", timeout=15000)
                    return (response.status, page.content()) if response else (0, "")

                yield fetch, Error
            finally:
                chromium.close()
    else:
        with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=15) as client:
            def fetch(url):
                response = client.get(url)
                return response.status_code, response.text

            yield fetch, httpx.TransportError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--after-id", type=int, default=0)
    parser.add_argument("--external-id", help="Check one known List.am listing")
    parser.add_argument("--delay", type=float, default=2)
    parser.add_argument("--browser", action="store_true", help="Read rendered pages with Playwright Chromium")
    parser.add_argument("--apply", action="store_true", help="Write photo URLs to the source rows")
    args = parser.parse_args()
    if args.limit < 1 or args.after_id < 0 or not math.isfinite(args.delay) or args.delay < 1:
        parser.error("limit must be positive, after-id nonnegative, and delay at least one second")

    with psycopg.connect(connect_timeout=5, autocommit=True) as conn, open_detail_pages(args.browser) as reader:
        fetch, request_error = reader
        rows = conn.execute(f"""
            SELECT id, external_id FROM public.listings
            WHERE source = 'list.am' AND is_active AND id > %s AND ({MISSING_IMAGES})
              AND (%s::text IS NULL OR external_id = %s)
            ORDER BY id LIMIT %s
        """, (args.after_id, args.external_id, args.external_id, args.limit)).fetchall()

        last_id = args.after_id
        found = updated = 0
        for listing_id, external_id in rows:
            if re.fullmatch(r"[0-9]+", external_id or ""):
                try:
                    status, html = fetch(f"https://www.list.am/item/{external_id}")
                except request_error:
                    print(f"Request failed. Resume with --after-id {last_id}.", file=sys.stderr)
                    return 1
                if status not in (200, 404, 410):
                    print(f"List.am returned HTTP {status}. Resume with --after-id {last_id}.",
                          file=sys.stderr)
                    return 1
                if status == 200:
                    images = [url for url in extract_images(BeautifulSoup(html, "html.parser"))
                              if url.startswith("https://img.list.am/f/")]
                    if not images and looks_blocked(html):
                        print(f"List.am blocked the request. Resume with --after-id {last_id}.", file=sys.stderr)
                        return 1
                    if images:
                        found += 1
                        print(f"Listing {external_id}: {len(images)} photo URLs")
                        if args.apply:
                            updated += conn.execute(f"""
                                UPDATE public.listings
                                SET raw_data = jsonb_set(
                                    CASE WHEN jsonb_typeof(raw_data::jsonb) = 'object'
                                         THEN raw_data::jsonb ELSE '{{}}'::jsonb END,
                                    '{{images}}', to_jsonb(%s::text[])
                                )::json
                                WHERE id = %s AND source = 'list.am' AND is_active AND ({MISSING_IMAGES})
                            """, (images, listing_id)).rowcount
                time.sleep(args.delay)
            last_id = listing_id

    print(f"Checked: {len(rows)}. With photos: {found}. Updated: {updated}. Next --after-id {last_id}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
