import click
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .scraper import ListingPipeline
from .normalizer import normalize_price
from .loader import process_scraped_item
DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/fairrent"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

@click.group()
def cli():
    """FairRent Ingestion Pipeline CLI"""
    pass

@cli.command()
@click.option("--pages", default=1, help="Number of pages to scrape.")
def run(pages):
    click.echo(f"Starting collection pipeline for {pages} page(s)...")
    
    pipeline = ListingPipeline()
    session = SessionLocal()
    
    processed_count = 0
    success_count = 0
    
    # Mock sample raw items (in the future, this will come from HTML parsing)
    mock_raw_items = [
        {"id": "101", "title": "2-room apartment in Kentron", "price": 400000, "currency": "AMD", "period": "month", "lat": 40.1792, "lon": 44.5151, "url": "https://list.am/item/101"},
        {"id": "102", "title": "Invalid price test", "price": -500, "currency": "USD", "period": "month", "lat": 40.18, "lon": 44.52, "url": "https://list.am/item/102"},
        {"id": "103", "title": "1-room studio in Arabkir", "price": 600, "currency": "USD", "period": "month", "lat": 40.19, "lon": 44.53, "url": "https://list.am/item/103"}
    ]
    
    try:
        for item in mock_raw_items:
            processed_count += 1
            validated = pipeline.parse_and_validate_record(item)
            
            if validated:
                normalized = normalize_price(
                    validated["price"], 
                    validated["currency"], 
                    validated["period"]
                )
                
                # Save into PostgreSQL database safely with idempotency & price history
                process_scraped_item(session, validated, normalized)
                success_count += 1
                click.echo(f"  [SAVED TO DB] Listing {validated['id']} -> {normalized['monthly_usd']} USD/month")
                
    finally:
        session.close()
        
    click.echo("\n--- Run Summary ---")
    click.echo(f"Total Processed: {processed_count}")
    click.echo(f"Successfully Saved: {success_count}")
    click.echo(f"Quarantined / Rejected: {len(pipeline.quarantine_log)}")

if __name__ == "__main__":
    cli()