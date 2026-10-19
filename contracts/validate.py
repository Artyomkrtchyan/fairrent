"""Validate the contract and shared scenarios; run from any directory."""
import json
from copy import deepcopy
from pathlib import Path
from statistics import mean, stdev
from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import validate_spec

root = Path(__file__).resolve().parent
spec = json.loads((root / 'openapi.json').read_text(encoding='utf-8'))
fixtures = json.loads((root / 'fixtures.json').read_text(encoding='utf-8'))
validate_spec(spec)
schemas = spec['components']['schemas']

def validator(name):
    return Draft202012Validator({'$ref': f'#/components/schemas/{name}', 'components': spec['components']}, format_checker=FormatChecker())

for name, fixture in fixtures.items():
    validator(fixture['schema']).validate(fixture['value'])

negative = [
    ('ValuationRequest', {'latitude': 91, 'longitude': 44}),
    ('ValuationRequest', {'latitude': 40, 'longitude': 181}),
    ('ValuationRequest', {'latitude': 40, 'longitude': 44, 'radius_m': 99}),
    ('ValuationRequest', {'latitude': 40, 'longitude': 44, 'window_days': 91}),
    ('ValuationRequest', {'latitude': 40, 'longitude': 44, 'unexpected': True}),
    ('ValuationRequest', {'latitude': 40, 'longitude': 44, 'area_sqm': 0}),
    ('ValuationRequest', {'latitude': 40, 'longitude': 44, 'renovation': 'invented'}),
    ('ValuationRequest', {'latitude': 40, 'longitude': 44, 'property': {'area_m2': 50}}),
    ('ReviewUpdate', {'status': 'resolved', 'decision': 'dismissed', 'reason': '  ', 'version': 1}),
    ('ReviewUpdate', {'status': 'resolved', 'decision': 'dismissed', 'reason': 'checked', 'version': 0}),
    ('ReviewUpdate', {'status': 'resolved', 'decision': None, 'reason': 'checked', 'version': 1}),
    ('ReviewUpdate', {'status': 'in_review', 'decision': 'dismissed', 'reason': 'checked', 'version': 1}),
]
bad_interval = deepcopy(fixtures['area-reference']['value']['ml_prediction_interval'])
bad_interval['confidence_level'] = 0.95
negative.append(('PredictionInterval', bad_interval))
bad_sparse = deepcopy(fixtures['valuation-sparse']['value']['observed_market_statistics'])
bad_sparse['observed_price_std_dev_usd'] = 0
negative.append(('ObservedMarketStatistics', bad_sparse))
bad_abstention = deepcopy(fixtures['valuation-sparse']['value'])
bad_abstention['valuation_assessment']['estimated_price_usd'] = 500
negative.append(('ValuationResponse', bad_abstention))
bad_input = {'latitude':40,'longitude':44,'as_of':'2026-10-17T08:00:00Z','radius_m':1000,'window_days':30,'asking_price_usd_month':600}
negative.append(('ModelInput', bad_input))
for schema, payload in negative:
    assert list(validator(schema).iter_errors(payload)), (schema, payload)

for operations in spec['paths'].values():
    for op in operations.values():
        for response in op['responses'].values():
            media = response['content']['application/json']
            if 'example' in media:
                schema = media['schema']['$ref'].split('/')[-1]
                validator(schema).validate(media['example'])
        if 'requestBody' in op:
            media = op['requestBody']['content']['application/json']
            validator(media['schema']['$ref'].split('/')[-1]).validate(media['example'])

prices = [500, 600, 700]
monthly = fixtures['valuation']['value']['observed_market_statistics']

assert monthly['comparables_count'] == len(prices)
assert monthly['cluster_mean_price_usd'] == mean(prices)
assert monthly['observed_price_std_dev_usd'] == stdev(prices)
assert fixtures['valuation-sparse']['value']['observed_market_statistics']['observed_price_std_dev_usd'] is None
assert all(value is None for value in fixtures['area-reference']['value']['ml_prediction_interval'].values())
assert monthly['cluster_mean_price_per_sqm_usd'] == mean([p / 50 for p in prices])
assert monthly['observed_price_std_dev_per_sqm_usd'] == stdev([p / 50 for p in prices])
assert fixtures['listings-truncated']['value']['has_more'] is True
assert fixtures['exchange-rate-unavailable']['value']['amd_per_usd'] is None
assert fixtures['listing-source-mapping']['value']['building_type_raw'] == 'new_building'
assert fixtures['listing-source-mapping']['value']['building_type'] is None
print(f'Valid OpenAPI: {len(schemas)} schemas, {len(fixtures)} fixtures, {len(negative)} rejected inputs, embedded examples.')
