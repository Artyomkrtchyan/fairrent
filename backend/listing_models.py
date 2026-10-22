"""C03 public listing contract; ingestion must supply source provenance explicitly."""
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Conversion(ContractModel):
    rate_to_usd: float = Field(gt=0)
    rate_date: date
    rate_source: str = Field(min_length=1)


class ListingData(ContractModel):
    id: UUID
    source: Literal["list.am"]
    external_id: str = Field(min_length=1)
    source_url: HttpUrl
    property_id: UUID | None
    title: str | None = Field(min_length=1)
    description: str | None = Field(min_length=1)
    address: str | None = Field(min_length=1)
    district_id: str | None = Field(min_length=1)
    latitude: float | None = Field(ge=-90, le=90)
    longitude: float | None = Field(ge=-180, le=180)
    coordinate_confidence: Literal["exact", "approximate", "unknown"]
    price_original: float = Field(gt=0)
    currency_original: Literal["USD", "AMD", "EUR", "RUB"]
    price_monthly_normalized: float | None = Field(gt=0)
    currency_normalized: Literal["USD"]
    conversion: Conversion | None
    utilities_included: bool | None
    rooms: int | None = Field(ge=1)
    floor: int | None = Field(ge=0)
    total_floors: int | None = Field(ge=1)
    area_sqm: float | None = Field(gt=0)
    published_at: datetime | None
    first_seen_at: datetime
    last_seen_at: datetime
    status: Literal["active", "inactive"]
    dedup_group_id: str | None = Field(min_length=1)
    renovation: Literal["cosmetic", "designer", "none"] | None
    building_type: Literal["monolith", "stone", "panel"] | None
    building_type_raw: str | None = Field(min_length=1)
    thumbnail_url: HttpUrl | None

    @model_validator(mode="after")
    def check_evidence(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Coordinates must be a pair")
        if self.latitude is None and self.coordinate_confidence != "unknown":
            raise ValueError("Missing coordinates require unknown confidence")
        if self.floor is not None and self.total_floors is not None and self.floor > self.total_floors:
            raise ValueError("Floor exceeds total floors")
        if (self.conversion is None) != (self.price_monthly_normalized is None):
            raise ValueError("Normalized price requires conversion provenance")
        for value in (self.published_at, self.first_seen_at, self.last_seen_at):
            if value is not None and (value.tzinfo is None or value.utcoffset() != timedelta(0)):
                raise ValueError("Observation timestamps must be UTC")
        if self.last_seen_at < self.first_seen_at:
            raise ValueError("Last seen precedes first seen")
        return self


class Freshness(ContractModel):
    data_as_of: datetime | None
    generated_at: datetime
    is_stale: bool
    max_age_days: int
    policy_version: str


class ListingResponse(ListingData):
    price_status: Literal["insufficient_data"] = "insufficient_data"
    freshness: Freshness


def public_listing(record: ListingData) -> ListingResponse:
    now = datetime.now(timezone.utc)
    return ListingResponse(**record.model_dump(), freshness=Freshness(
        data_as_of=record.last_seen_at, generated_at=now,
        is_stale=now - record.last_seen_at > timedelta(days=14),
        max_age_days=14, policy_version="freshness-proposal-v1",
    ))


class ListingPage(ContractModel):
    items: list[ListingResponse]
    page: int
    page_size: int
    total: int
    has_more: bool


class ListingDetail(ContractModel):
    listing: ListingResponse
    signals: list[dict] = Field(default_factory=list)
    estimate: None = None


class ListingQuery(ContractModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    district_id: str | None = Field(default=None, min_length=1)
    price_min: float | None = Field(default=None, ge=0)
    price_max: float | None = Field(default=None, ge=0)
    rooms: int | None = Field(default=None, ge=1)
    area_min: float | None = Field(default=None, gt=0)
    area_max: float | None = Field(default=None, gt=0)
    status: Literal["active", "inactive"] = "active"
    bbox: str | None = Field(default=None, pattern=r"^-?\d+(\.\d+)?,-?\d+(\.\d+)?,-?\d+(\.\d+)?,-?\d+(\.\d+)?$")
    sort: Literal["newest", "price_asc", "price_desc", "area_asc", "area_desc"] = "newest"

    @model_validator(mode="after")
    def check_ranges(self):
        for low, high in ((self.price_min, self.price_max), (self.area_min, self.area_max)):
            if low is not None and high is not None and low > high:
                raise ValueError("Minimum must not exceed maximum")
        if self.bbox is not None:
            west, south, east, north = self.bounds()
            if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
                raise ValueError("Invalid bounding box coordinates or order")
            if east - west > 0.5 + 1e-12 or north - south > 0.5 + 1e-12:
                raise ValueError("Bounding box span must not exceed 0.5 degrees per axis")
        return self

    def bounds(self):
        return tuple(float(value) for value in self.bbox.split(","))
