"""Bounded PostGIS candidate lookup and atomic estimate persistence."""
from datetime import datetime, time, timedelta
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg
from psycopg.types.json import Jsonb

try:
    from .listing_models import ListingData
except ImportError:
    from listing_models import ListingData


def period(as_of, days):
    end = as_of.astimezone(ZoneInfo('Asia/Yerevan')).date()
    start = end - timedelta(days=days - 1)
    return start, end, datetime.combine(start, time(), ZoneInfo('Asia/Yerevan'))


class ValuationRepository:
    def connection(self):
        return psycopg.connect(connect_timeout=3)

    def candidates(self, connection, query, now):
        _, _, start = period(now, query.window_days)
        # B03's maximum comparable age remains 60 days even for a 90-day query.
        start = max(start, now - timedelta(days=60))
        rows = connection.execute('''
            SELECT document FROM api_listing_projection
            WHERE status = 'active' AND latitude IS NOT NULL AND longitude IS NOT NULL
              AND price IS NOT NULL
              AND (document->>'last_seen_at')::timestamptz BETWEEN %s AND %s
              AND ST_DWithin(ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography,
                             ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)
            ORDER BY id LIMIT 10001
        ''', (start, now, query.longitude, query.latitude, query.radius_m * 1.01)).fetchall()
        if len(rows) > 10000:
            raise CandidateLimit('Too many comparable listings; reduce radius or window')
        records = [ListingData.model_validate(row[0]) for row in rows]
        version = sha256(json.dumps([r.model_dump(mode='json') for r in records],
                                    sort_keys=True).encode()).hexdigest()
        return records, version

    def save(self, connection, query, result, dataset_version, coverage_version):
        connection.execute('''INSERT INTO api_valuation_estimates
            (request_id, generated_at, data_as_of, dataset_version, model_version,
             policy_version, coverage_version, request_document, response_document)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
            (result['request_id'], result['freshness']['generated_at'],
             result['freshness']['data_as_of'], dataset_version,
             result['versions']['model_version'], result['cohort']['selection_version'],
             coverage_version, Jsonb(query.model_dump(mode='json', exclude_none=True)), Jsonb(result)))


class CandidateLimit(RuntimeError):
    pass


def migrate():
    with psycopg.connect(connect_timeout=3) as connection:
        connection.execute((Path(__file__).parent / 'sql' / '002_valuation_estimates.sql').read_text(encoding='utf-8-sig'))


if __name__ == '__main__':
    migrate()
