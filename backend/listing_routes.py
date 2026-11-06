from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

try:
    from .listing_models import ListingDetail, ListingFilters, ListingMapPoint, ListingPage, ListingQuery, public_listing
    from .listing_repository import ListingRepository
    from .valuation_coverage import OutsideCoverage
    from .valuation_models import ValuationRequest
    from .valuation_repository import CandidateLimit
    from .valuation_routes import service
except ImportError:
    from listing_models import ListingDetail, ListingFilters, ListingMapPoint, ListingPage, ListingQuery, public_listing
    from listing_repository import ListingRepository
    from valuation_coverage import OutsideCoverage
    from valuation_models import ValuationRequest
    from valuation_repository import CandidateLimit
    from valuation_routes import service


router = APIRouter(prefix="/api/v1/listings", tags=["listings"])


def repository():
    return ListingRepository()


def unique_query(request: Request):
    keys = list(request.query_params.keys())
    if any(len(request.query_params.getlist(key)) != 1 for key in keys):
        raise HTTPException(422, "Repeated query parameters are not supported")


@router.get("", response_model=ListingPage, dependencies=[Depends(unique_query)])
def listings(query: Annotated[ListingQuery, Query()], repo=Depends(repository)):
    records, total = repo.search(query)
    return ListingPage(items=[public_listing(record) for record in records],
                       page=query.page, page_size=query.page_size,
                       total=total, has_more=query.page * query.page_size < total)


@router.get("/map", response_model=list[ListingMapPoint], dependencies=[Depends(unique_query)])
def listing_map(query: Annotated[ListingFilters, Query()], repo=Depends(repository)):
    return repo.map_points(query)


@router.get("/{id}", response_model=ListingDetail)
def listing_detail(id: UUID, request: Request, repo=Depends(repository)):
    if request.query_params:
        raise HTTPException(422, "This endpoint accepts no query parameters")
    record, signals = repo.detail(id)
    if record is None:
        raise HTTPException(404, "Listing not found")
    return ListingDetail(listing=public_listing(record),
                         signals=[s.model_dump(mode="json") for s in signals], image_urls=record.image_urls)


@router.get("/{id}/estimate")
def listing_estimate(id: UUID, request: Request, repo=Depends(repository), evaluator=Depends(service)):
    if request.query_params:
        raise HTTPException(422, "This endpoint accepts no query parameters")
    record = repo.get(id)
    if (record is None or record.status != "active" or record.coordinate_confidence == "unknown"
            or record.latitude is None or record.longitude is None):
        raise HTTPException(404, "Listing estimate unavailable")
    fields = ("latitude", "longitude", "area_sqm", "rooms", "floor", "total_floors",
              "renovation", "building_type")
    inputs = {key: getattr(record, key) for key in fields}
    if record.price_monthly_normalized is not None:
        inputs["asking_price_usd_month"] = record.price_monthly_normalized
    query = ValuationRequest(**inputs)
    try:
        return evaluator.assess(query, request.state.request_id, subject=record, persist=False)
    except (OutsideCoverage, CandidateLimit) as exc:
        raise HTTPException(404, "Listing estimate unavailable") from exc
