"""C01 reviewer queue contracts. Decisions require a reason and current version."""
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import Field, field_serializer, model_validator

try:
    from .listing_models import ContractModel, ListingResponse
except ImportError:
    from listing_models import ContractModel, ListingResponse

Status = Literal["pending", "in_review", "resolved"]
Decision = Literal["dismissed", "needs_follow_up", "confirmed_issue"]


class ReviewEvent(ContractModel):
    status: Status
    decision: Decision | None
    reason: str
    actor_id: UUID
    created_at: datetime

    @field_serializer("created_at")
    def utc_time(self, value):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class RiskSignal(ContractModel):
    id: UUID
    listing_id: UUID
    category: Literal["price_anomaly", "risk_evidence"]
    rule_id: str = Field(min_length=1)
    rules_version: str = Field(min_length=1)
    evidence: list[str] = Field(min_length=1)
    created_at: datetime
    explanation: str = Field(min_length=1)

    @field_serializer("created_at")
    def utc_time(self, value):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class Review(ContractModel):
    id: UUID
    listing_id: UUID
    signal_ids: list[UUID]
    status: Status
    decision: Decision | None
    reason: str | None
    reviewed_at: datetime | None
    updated_at: datetime
    version: int = Field(ge=1)
    history: list[ReviewEvent]
    listing: ListingResponse
    signals: list[RiskSignal]

    @model_validator(mode="after")
    def consistent_subject(self):
        if self.listing.id != self.listing_id or any(s.listing_id != self.listing_id for s in self.signals):
            raise ValueError("Review evidence must belong to its listing")
        if len(set(self.signal_ids)) != len(self.signal_ids) or set(self.signal_ids) != {s.id for s in self.signals}:
            raise ValueError("Review signal IDs must match its evidence")
        return self

    @field_serializer("reviewed_at", "updated_at")
    def utc_time(self, value):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if value else None


class ReviewPage(ContractModel):
    items: list[Review]
    page: int
    page_size: int
    total: int
    has_more: bool


class ReviewQuery(ContractModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    status: Status | None = None
    listing_id: UUID | None = None


class ReviewUpdate(ContractModel):
    status: Literal["in_review", "resolved"]
    decision: Decision | None
    reason: str = Field(min_length=1, max_length=2000)
    version: int = Field(ge=1, strict=True)

    @model_validator(mode="after")
    def valid_decision(self):
        if not self.reason.strip():
            raise ValueError("A nonblank decision reason is required")
        if (self.status == "resolved") != (self.decision is not None):
            raise ValueError("A decision is required only when resolving a review")
        return self
