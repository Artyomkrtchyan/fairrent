"""C06 public market-index contract, backed by published A07 asking rents."""
from datetime import date, datetime, timedelta, timezone
import re
from typing import Literal

from pydantic import Field, field_validator, model_validator

try:
    from .listing_models import ContractModel, Freshness
except ImportError:
    from listing_models import ContractModel, Freshness


class MarketQuery(ContractModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    district_id: str | None = Field(default=None, min_length=1)
    period_start: date | None = None
    period_end: date | None = None

    @field_validator("period_start", "period_end", mode="before")
    @classmethod
    def iso_date(cls, value):
        if isinstance(value, str) and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("Expected an ISO date (YYYY-MM-DD)")
        return value

    @model_validator(mode="after")
    def ordered_dates(self):
        if self.period_start is not None and self.period_end is not None:
            if self.period_start > self.period_end:
                raise ValueError("period_start must not exceed period_end")
        return self


class MarketAggregate(ContractModel):
    district_id: str = Field(min_length=1)
    period_start: date
    period_end: date
    sample_count: int = Field(ge=0)
    area_sample_count: int = Field(ge=0)
    median_usd_month: float | None = Field(gt=0)
    median_usd_m2: float | None = Field(gt=0)
    status: Literal["available", "insufficient_data"]
    data_as_of: datetime | None
    measure: Literal["asking_price"] = "asking_price"


class MarketIndex(MarketAggregate):
    freshness: Freshness


class MarketIndexPage(ContractModel):
    items: list[MarketIndex]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
    has_more: bool
    available_from: date | None
    available_to: date | None


def public_market_index(record: MarketAggregate, generated_at: datetime) -> MarketIndex:
    data_as_of = record.data_as_of.astimezone(timezone.utc) if record.data_as_of else None
    return MarketIndex(**{**record.model_dump(), "data_as_of": data_as_of}, freshness=Freshness(
        data_as_of=data_as_of, generated_at=generated_at,
        is_stale=data_as_of is None or generated_at - data_as_of > timedelta(days=14),
        max_age_days=14, policy_version="freshness-proposal-v1",
    ))
