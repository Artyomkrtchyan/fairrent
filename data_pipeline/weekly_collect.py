"""Bounded CloakBrowser collection with explicit, hash-bound completion evidence."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from uuid import uuid4

from bs4 import BeautifulSoup

from .scrape_listam import BASE, CATEGORY, build_record, extract_map_points, is_yerevan, parse_cards, parse_detail
from .scraper import looks_blocked


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def collect(fetch, *, max_pages, details_limit):
    records, seen = {}, set()
    complete = False
    pages = 0
    for number in range(1, max_pages + 1):
        url = BASE + CATEGORY + ('' if number == 1 else f'/{number}')
        html = fetch(url)
        if looks_blocked(html):
            raise ValueError('Source challenge or error page')
        soup = BeautifulSoup(html, 'html.parser')
        cards = parse_cards(html)
        if not cards:
            # Only a recognizable empty catalogue after observed inventory is
            # terminal evidence. Missing cards alone are never sufficient.
            if number > 1 and soup.select_one('#contentr') is not None and not soup.select('a[href*="/item/"]'):
                complete = True
                pages += 1
                break
            raise ValueError('Empty or changed catalogue; completion not established')
        ids = {card['id'] for card in cards}
        if not ids - seen:
            raise ValueError('Repeated catalogue page; completion not established')
        seen.update(ids)
        coordinates, _ = extract_map_points(html)
        for card in cards:
            record = build_record(card, coordinates, None)  # retain source currency/price
            if is_yerevan(record) and record['period'] == 'month':
                records[record['external_id']] = record
        pages += 1
    if not records:
        raise ValueError('No monthly Yerevan rentals; refusing empty publication')
    visits = list(records.values())
    if len(visits) > details_limit:
        complete = False
    for record in visits[:details_limit]:
        html = fetch(record['url'])
        if looks_blocked(html) or BeautifulSoup(html, 'html.parser').select_one('h1') is None:
            raise ValueError('Missing or blocked detail page')
        detail = parse_detail(html)
        record['utilities_included'] = detail['utilities_included']
        if record['lat'] is None and detail['lat'] is not None:
            record.update(lat=detail['lat'], lon=detail['lon'],
                          coordinate_source='list.am:detail-page-map', coordinate_confidence='approximate')
    # Only accepted segment IDs enter lifecycle bookkeeping, never unrelated
    # sales/daily rentals. Quarantine in the importer disables staleness too.
    return list(records.values()), complete, pages


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--max-pages', type=int, default=50)
    parser.add_argument('--details-limit', type=int, default=2000)
    parser.add_argument('--delay', type=float, default=3)
    args = parser.parse_args(argv)
    if args.max_pages < 1 or args.details_limit < 0 or args.delay < 1:
        parser.error('positive page cap, nonnegative detail cap and delay >= 1 required')
    report_path = args.output.with_suffix('.report.json')
    report = dict(schema_version=1, snapshot_id=uuid4().hex, source='list.am', segment='yerevan-monthly-rentals',
                  started_at=utcnow(), status='running', complete=False)
    atomic_json(report_path, report)
    context = None
    try:
        from cloakbrowser import launch_persistent_context
        context = launch_persistent_context(str(args.profile), headless=True, chromium_sandbox=True)
        page = context.new_page()

        def fetch(url):
            # At most two requests; navigation/network exceptions are bounded by
            # Playwright and the outer process timeout. Never log exception text
            # that could contain a proxy or license credential.
            for attempt in range(2):
                time.sleep(args.delay * (attempt + 1))
                response = page.goto(url, wait_until='domcontentloaded', timeout=45000)
                if response is not None and response.status == 200 and page.url.rstrip('/') == url.rstrip('/'):
                    html = page.content()
                    if not looks_blocked(html):
                        return html
            raise ValueError('Source request failed after bounded retries')

        records, complete, pages = collect(fetch, max_pages=args.max_pages, details_limit=args.details_limit)
        atomic_json(args.output, records)
        report.update(status='success' if complete else 'partial', complete=complete,
                      records=len(records), pages_fetched=pages,
                      sha256=hashlib.sha256(args.output.read_bytes()).hexdigest())
    except Exception as error:
        report.update(status='failed', error_type=type(error).__name__)
    finally:
        if context is not None:
            try:
                context.close()
            except Exception:
                report.update(status='failed', complete=False, error_type='BrowserCloseError')
        report['finished_at'] = utcnow()
        atomic_json(report_path, report)
    return 0 if report['status'] in ('success', 'partial') else 1


if __name__ == '__main__':
    raise SystemExit(main())
