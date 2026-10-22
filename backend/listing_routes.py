from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

try:
    from .listing_models import ListingDetail, ListingPage, ListingQuery, public_listing
    from .listing_repository import ListingRepository
except ImportError:
    from listing_models import ListingDetail, ListingPage, ListingQuery, public_listing
    from listing_repository import ListingRepository


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


@router.get("/{id}", response_model=ListingDetail)
def listing_detail(id: UUID, request: Request, repo=Depends(repository)):
    if request.query_params:
        raise HTTPException(422, "This endpoint accepts no query parameters")
    record = repo.get(id)
    if record is None:
        raise HTTPException(404, "Listing not found")
    return ListingDetail(listing=public_listing(record))
