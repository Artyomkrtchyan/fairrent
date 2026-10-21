import click
from scraper import ListingPipeline
from normalizer import normalize_price

@click.group()
def cli():
    """FairRent Ingestion Pipeline CLI"""
    pass

@cli.command()
@click.option("--pages", default=1, help="Number of pages to scrape.")
def run(pages):
    click.echo(f"Starting collection pipeline for {pages} page(s)...")
    
    pipeline = ListingPipeline()
    processed_count = 0
    success_count = 0
    
    # Mock sample raw items fetched from list.am for demonstration
    mock_raw_items = [
        {"id": "101", "price": 400000, "currency": "AMD", "period": "month", "lat": 40.1792, "lon": 44.5151},
        {"id": "102", "price": -500, "currency": "USD", "period": "month", "lat": 40.18, "lon": 44.52}, 
        {"id": "103", "price": 600, "currency": "USD", "period": "month", "lat": 40.19, "lon": 44.53}
    ]
    
    for item in mock_raw_items:
        processed_count += 1
        validated = pipeline.parse_and_validate_record(item)
        
        if validated:
            normalized = normalize_price(
                validated["price"], 
                validated["currency"], 
                validated["period"]
            )
            success_count += 1
            click.echo(f"  [SUCCESS] Listing {validated['id']} -> {normalized['monthly_usd']} USD/month")
            
    click.echo("\n--- Run Summary ---")
    click.echo(f"Total Processed: {processed_count}")
    click.echo(f"Successfully Normalized: {success_count}")
    click.echo(f"Quarantined / Rejected: {len(pipeline.quarantine_log)}")

if __name__ == "__main__":
    cli()