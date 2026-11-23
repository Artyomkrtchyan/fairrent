"""Read-only map points from the versioned A05 reference registry."""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import Field, model_validator

from data_pipeline.geography import reference_points

try:
    from .listing_models import ContractModel, ListingFilters
    from .listing_routes import unique_query
except ImportError:
    from listing_models import ContractModel, ListingFilters
    from listing_routes import unique_query


router = APIRouter(prefix="/api/v1/infrastructure", tags=["infrastructure"])


class InfrastructureQuery(ContractModel):
    bbox: str
    type: Literal["metro", "university"] | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def validate_bounds(self):
        ListingFilters(bbox=self.bbox)
        return self


class InfrastructurePoint(ContractModel):
    id: str
    name: str
    type: Literal["metro", "university"]
    latitude: float
    longitude: float


class InfrastructurePage(ContractModel):
    items: list[InfrastructurePoint]
    page: int
    page_size: int
    total: int
    has_more: bool


@router.get("", response_model=InfrastructurePage, dependencies=[Depends(unique_query)])
def infrastructure(query: Annotated[InfrastructureQuery, Query()]):
    west, south, east, north = ListingFilters(bbox=query.bbox).bounds()
    points = [
        InfrastructurePoint(id=point["id"], name=point["name"], type=point["kind"],
                            latitude=point["latitude"], longitude=point["longitude"])
        for point in reference_points()
        if point["kind"] in ("metro", "university")
        and (query.type is None or point["kind"] == query.type)
        and west <= point["longitude"] <= east and south <= point["latitude"] <= north
    ]
    points.sort(key=lambda point: point.id)
    start = (query.page - 1) * query.page_size
    return InfrastructurePage(items=points[start:start + query.page_size], page=query.page,
                              page_size=query.page_size, total=len(points),
                              has_more=start + query.page_size < len(points))
