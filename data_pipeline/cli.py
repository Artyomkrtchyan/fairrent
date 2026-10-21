import json

import click
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from .config import DEFAULT_SOURCE_NAME, DEFAULT_SOURCE_URL, get_database_url
from .ingestion import finish_run, start_run
from .loader import process_scraped_item
from .normalizer import normalize_price
from .scraper import ListingPipeline

# Synthetic records, only used with `run --demo` (stored with source="demo").
DEMO_RECORDS = [
    {"id": "101", "title": "2-room apartment in Kentron", "price": 400000, "currency": "AMD", "period": "month", "lat": 40.1792, "lon": 44.5151, "url": "https://example.invalid/item/101"},
    {"id": "102", "title": "Invalid price test", "price": -500, "currency": "USD", "period": "month", "lat": 40.18, "lon": 44.52, "url": "https://example.invalid/item/102"},
    {"id": "103", "title": "1-room studio in Arabkir", "price": 600, "currency": "USD", "period": "month", "lat": 40.19, "lon": 44.53, "url": "https://example.invalid/item/103"},
]


def get_session_factory():
    """Builds the session factory from project configuration (DATABASE_URL)."""
    engine = create_engine(get_database_url(), pool_pre_ping=True)
    return sessionmaker(bind=engine)


def load_records(path: str) -> list:
    """Reads a JSON file holding one record or a list of records (raw-item or parser schema)."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    records = data if isinstance(data, list) else [data]
    for rec in records:
        if "id" not in rec and "external_id" in rec:
            rec["id"] = rec["external_id"]
    return records


def ingest(items, pipeline: ListingPipeline, session, source: str, run_id=None) -> int:
    """Validate -> normalize -> load each raw item. Returns the number saved."""
    saved = 0
    for item in items:
        validated = pipeline.parse_and_validate_record(item)
        if validated is None:
            continue
        validated["source"] = source
        try:
            normalized = normalize_price(
                validated["price"], validated["currency"], validated["period"],
                includes_utilities=validated.get("utilities_included"),
            )
        except ValueError as e:
            pipeline.quarantine(item, str(e))
            continue
        try:
            process_scraped_item(session, validated, normalized, run_id=run_id)
        except SQLAlchemyError as e:
            session.rollback()
            pipeline.quarantine(item, f"Database error: {e}")
            continue
        saved += 1
        click.echo(f"  [SAVED] {source}/{validated['id']} -> {normalized['monthly_usd']} USD/month "
                   f"({normalized['monthly_amd']} AMD/month)")
    return saved


def _summary(run, saved: int, quarantined: int) -> None:
    click.echo("\n--- Run Summary ---")
    click.echo(f"Run id: {run.id if run is not None else '-'}")
    if run is not None:
        click.echo(f"Status: {run.status} (complete crawl: {run.is_complete})")
        click.echo(f"Listings seen on source: {run.listings_seen}")
        click.echo(f"Deactivated (staleness policy): {run.listings_deactivated}")
        if run.notes:
            click.echo(f"Notes: {run.notes}")
    click.echo(f"Total Processed: {saved + quarantined}")
    click.echo(f"Successfully Saved: {saved}")
    click.echo(f"Quarantined / Rejected: {quarantined}")


@click.group()
def cli():
    """FairRent Ingestion Pipeline CLI"""


@cli.command()
@click.option("--pages", default=1, type=click.IntRange(min=1),
              help="Maximum number of index pages. A run only counts as COMPLETE if pagination "
                   "ends (an empty page is reached) before this cap.")
@click.option("--source-url", default=DEFAULT_SOURCE_URL, show_default=True,
              help="Listing index URL (use a project-owned server for testing).")
@click.option("--source-name", default=DEFAULT_SOURCE_NAME, show_default=True,
              help="Source label stored with every listing. Use one name per collected segment: "
                   "staleness is evaluated per source name.")
@click.option("--delay", default=1.0, type=click.FloatRange(min=0), show_default=True,
              help="Seconds to wait between HTTP requests.")
@click.option("--max-listings", type=click.IntRange(min=1), default=None,
              help="Stop after this many listing pages (makes the run partial).")
@click.option("--demo", is_flag=True,
              help="Insert built-in synthetic records (source 'demo') instead of collecting.")
def run(pages, source_url, source_name, delay, max_listings, demo):
    try:
        session_factory = get_session_factory()
    except RuntimeError as e:
        raise click.ClickException(str(e))

    pipeline = ListingPipeline(delay=delay)
    session = session_factory()
    run_row = None
    try:
        if demo:
            click.echo("DEMO MODE: inserting synthetic records with source 'demo' "
                       "(--pages/--source-url ignored, no run is recorded).")
            saved = ingest(DEMO_RECORDS, pipeline, session, "demo")
        else:
            click.echo(f"Collecting up to {pages} page(s) from {source_url} as '{source_name}' ...")
            run_row = start_run(session, source_name, {
                "source_url": source_url, "pages": pages, "delay": delay, "max_listings": max_listings})
            saved = 0
            try:
                saved = ingest(pipeline.collect(source_url, pages, max_listings),
                               pipeline, session, source_name, run_id=run_row.id)
            except Exception as e:  # unexpected failure: record it, never deactivate anything
                session.rollback()
                finish_run(session, run_row, seen_ids=(), error=repr(e), stats={
                    "listings_saved": saved, "listings_quarantined": len(pipeline.quarantine_log)})
                raise click.ClickException(f"Run {run_row.id} failed: {e!r}")
            finish_run(
                session, run_row, seen_ids=pipeline.seen_ids, crawl_complete=pipeline.crawl_complete,
                stats={"pages_requested": pipeline.pages_requested, "pages_fetched": pipeline.pages_fetched,
                       "listings_seen": len(pipeline.seen_ids), "listings_saved": saved,
                       "listings_quarantined": len(pipeline.quarantine_log)})
        _summary(run_row, saved, len(pipeline.quarantine_log))
    finally:
        session.close()
        pipeline.close()


@cli.command("import-file")
@click.argument("path", type=click.Path(exists=True, dir_okay=False))
@click.option("--source-name", default="fixture", show_default=True,
              help="Source label for the imported records.")
def import_file(path, source_name):
    """Reproducible fallback import from a local JSON file (use when the source is unreachable).

    Goes through the same validation, normalization and loading as a crawl, but never
    deactivates anything.
    """
    try:
        session_factory = get_session_factory()
    except RuntimeError as e:
        raise click.ClickException(str(e))
    records = load_records(path)

    pipeline = ListingPipeline(delay=0)
    session = session_factory()
    try:
        run_row = start_run(session, source_name, {"file": path})
        saved = ingest(records, pipeline, session, source_name, run_id=run_row.id)
        finish_run(session, run_row, crawl_complete=None, stats={
            "listings_seen": len(records), "listings_saved": saved,
            "listings_quarantined": len(pipeline.quarantine_log)})
        _summary(run_row, saved, len(pipeline.quarantine_log))
    finally:
        session.close()
        pipeline.close()


if __name__ == "__main__":
    cli()
