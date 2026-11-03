"""C01 valuation input and runtime response validation."""
import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from jsonschema import Draft202012Validator, FormatChecker
from pydantic import Field, model_validator

try:
    from .listing_models import ContractModel
except ImportError:
    from listing_models import ContractModel


class ValuationRequest(ContractModel):
    latitude: float = Field(ge=-90, le=90, strict=True)
    longitude: float = Field(ge=-180, le=180, strict=True)
    radius_m: int = Field(default=1000, ge=100, le=5000, strict=True)
    window_days: int = Field(default=30, ge=7, le=90, strict=True)
    asking_price_usd_month: float | None = Field(default=None, gt=0, strict=True)
    rooms: int | None = Field(default=None, ge=1, strict=True)
    floor: int | None = Field(default=None, ge=0, strict=True)
    total_floors: int | None = Field(default=None, ge=1, strict=True)
    area_sqm: float | None = Field(default=None, gt=0, strict=True)
    renovation: Literal['cosmetic', 'designer', 'none'] | None = None
    building_type: Literal['monolith', 'stone', 'panel'] | None = None

    @model_validator(mode='after')
    def validate_features(self):
        if self.floor is not None and self.total_floors is not None and self.floor > self.total_floors:
            raise ValueError('Floor exceeds total floors')
        if 'asking_price_usd_month' in self.model_fields_set and self.asking_price_usd_month is None:
            raise ValueError('Omit unknown asking_price_usd_month')
        return self


@lru_cache
def response_validator():
    root = Path(__file__).resolve().parents[1]
    spec = json.loads((root / 'contracts' / 'openapi.json').read_text(encoding='utf-8'))
    return Draft202012Validator({'$ref': '#/components/schemas/ValuationResponse',
                                'components': spec['components']}, format_checker=FormatChecker())


def validate_response(value):
    json.dumps(value, allow_nan=False)
    response_validator().validate(value)
    return value
