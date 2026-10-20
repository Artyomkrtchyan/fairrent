from datetime import datetime, timezone
from sqlalchemy.orm import Session
from database.models import Property, Listing, PriceObservation

def process_scraped_item(session: Session, data: dict, normalized: dict):
    """
    Ingests a parsed listing, ensuring idempotency via external_id,
    updating property records, and recording price history observations.
    """
    external_id = data["id"]
    
    # 1. Link or create the master Property record (spatial data)
    property_record = session.query(Property).join(Listing).filter(Listing.external_id == external_id).first()
    
    if not property_record:
        property_record = Property(
            geom=f"POINT({data['lon']} {data['lat']})"
        )
        session.add(property_record)
        session.flush()
        
    # 2. Upsert the Listing record using external_id
    listing_record = session.query(Listing).filter(Listing.external_id == external_id).first()
    
    new_price_usd = normalized["monthly_usd"]
    orig_curr = normalized.get("original_currency", "USD")
    orig_price = normalized.get("original_price", new_price_usd)
    new_price_amd = orig_price if orig_curr == "AMD" else new_price_usd * 385.0

    if not listing_record:
        listing_record = Listing(
            property_id=property_record.id,
            external_id=external_id,
            title=data.get("title"),
            price_usd=new_price_usd,
            price_amd=new_price_amd,
            raw_data=data
        )
        session.add(listing_record)
    else:
        # Update current listing fields with latest values
        listing_record.title = data.get("title", listing_record.title)
        listing_record.price_usd = new_price_usd
        listing_record.price_amd = new_price_amd
        listing_record.raw_data = data

    session.flush()

    # 3. Track price history by recording observations on change
    latest_obs = session.query(PriceObservation).filter(
        PriceObservation.listing_id == listing_record.id
    ).order_by(PriceObservation.recorded_at.desc()).first()
    
    if not latest_obs or latest_obs.price_usd != new_price_usd:
        observation = PriceObservation(
            listing_id=listing_record.id,
            price_usd=new_price_usd,
            price_amd=new_price_amd,
            recorded_at=datetime.now(timezone.utc)
        )
        session.add(observation)
        
    session.commit()