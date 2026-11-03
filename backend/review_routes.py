from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

try:
    from .listing_routes import unique_query
    from .review_models import Review, ReviewPage, ReviewQuery, ReviewUpdate
    from .review_repository import ReviewConflict, ReviewRepository
    from .reviewer_auth import require_reviewer
except ImportError:
    from listing_routes import unique_query
    from review_models import Review, ReviewPage, ReviewQuery, ReviewUpdate
    from review_repository import ReviewConflict, ReviewRepository
    from reviewer_auth import require_reviewer

router = APIRouter(prefix="/api/v1/reviews", tags=["reviews"], dependencies=[Depends(require_reviewer)])


def repository():
    return ReviewRepository()


@router.get("", response_model=ReviewPage, dependencies=[Depends(unique_query)])
def reviews(query: Annotated[ReviewQuery, Query()], repo=Depends(repository)):
    records, total = repo.search(query)
    return ReviewPage(items=records, page=query.page, page_size=query.page_size,
                      total=total, has_more=query.page * query.page_size < total)


@router.patch("/{id}", response_model=Review)
def update_review(id: UUID, update: ReviewUpdate, request: Request,
                  actor_id=Depends(require_reviewer), repo=Depends(repository)):
    if request.query_params:
        raise HTTPException(422, "This endpoint accepts no query parameters")
    try:
        record = repo.update(id, update, actor_id)
    except ReviewConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    if record is None:
        raise HTTPException(404, "Review not found")
    return record
