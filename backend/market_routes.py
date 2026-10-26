from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query

try:
    from .listing_routes import unique_query
    from .market_models import MarketIndexPage, MarketQuery, public_market_index
    from .market_repository import MarketRepository
except ImportError:
    from listing_routes import unique_query
    from market_models import MarketIndexPage, MarketQuery, public_market_index
    from market_repository import MarketRepository


router = APIRouter(prefix="/api/v1/market-index", tags=["market"])


def repository():
    return MarketRepository()


@router.get("", response_model=MarketIndexPage, dependencies=[Depends(unique_query)])
def market_index(query: Annotated[MarketQuery, Query()], repo=Depends(repository)):
    records, total, available_from, available_to = repo.search(query)
    generated_at = datetime.now(timezone.utc)
    return MarketIndexPage(
        items=[public_market_index(record, generated_at) for record in records],
        page=query.page, page_size=query.page_size, total=total,
        has_more=query.page * query.page_size < total,
        available_from=available_from, available_to=available_to,
    )
