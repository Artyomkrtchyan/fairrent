"""Validate the contract and shared scenarios; run from any directory."""
import json
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
    ('ReviewUpdate', {'status': 'resolved', 'decision': 'dismissed', 'reason': '  ', 'version': 1}),
    ('ReviewUpdate', {'status': 'resolved', 'decision': 'dismissed', 'reason': 'checked', 'version': 0}),
    ('ReviewUpdate', {'status': 'resolved', 'decision': None, 'reason': 'checked', 'version': 1}),
    ('ReviewUpdate', {'status': 'in_review', 'decision': 'dismissed', 'reason': 'checked', 'version': 1}),
]
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
monthly = fixtures['valuation']['value']['monthly']

assert monthly['count'] == len(prices)
assert monthly['mean'] == mean(prices)
assert monthly['sample_stddev'] == stdev(prices)
assert fixtures['valuation-sparse']['value']['monthly']['sample_stddev'] is None
print(f'Valid OpenAPI: {len(schemas)} schemas, {len(fixtures)} fixtures, {len(negative)} rejected inputs, embedded examples.')
