import logging
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_exponential

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ListingPipeline:
    def __init__(self):
        self.quarantine_log = []

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def fetch_page(self, url: str) -> str:
        """Fetches a page with bounded retries for network resilience."""
        import requests
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.text

    def parse_and_validate_record(self, raw_item: dict) -> dict:
        """
        Validates incoming record fields. 
        Quarantines record if critical fields (price, coordinates, ID) are missing/invalid.
        """
        try:
            # Check for mandatory fields
            if not raw_item.get("id") or not raw_item.get("price") or not raw_item.get("lat"):
                raise ValueError("Missing critical fields (id, price, or coordinates)")
                
            # Validate numeric constraints
            price = float(raw_item["price"])
            if price <= 0:
                raise ValueError("Price must be greater than zero")
                
            return raw_item
        except Exception as e:
            # Quarantine the bad record with reason
            quarantined_record = {
                "raw_data": raw_item,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
            self.quarantine_log.append(quarantined_record)
            logger.warning(f"Quarantined record due to: {e}")
            return None