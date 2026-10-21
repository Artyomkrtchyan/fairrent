"""Coverage is supplied by A05/operator, never inferred from demo coordinates."""
from hashlib import sha256
import json
import os
from pathlib import Path


class CoverageUnavailable(RuntimeError):
    pass


class OutsideCoverage(ValueError):
    pass


class Coverage:
    def __init__(self):
        try:
            value = json.loads(Path(os.environ['VALUATION_COVERAGE_FILE']).read_text(encoding='utf-8-sig'))
            props = value['properties']
            self.geometry = value['geometry']
            if value['type'] != 'Feature' or self.geometry['type'] not in {'Polygon', 'MultiPolygon'}:
                raise ValueError('Polygon Feature required')
            if not isinstance(props['version'], str) or not props['version'].strip():
                raise ValueError('Coverage version required')
            if not isinstance(props['source'], str) or not props['source'].strip():
                raise ValueError('Coverage provenance required')
            content = json.dumps(value, sort_keys=True)
            self.version = props['version'] + ':' + sha256(content.encode()).hexdigest()
        except (OSError, KeyError, TypeError, ValueError) as exc:
            raise CoverageUnavailable('Authoritative valuation coverage is not configured') from exc

    def check(self, connection, query):
        value = connection.execute('''
            WITH boundary AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(%s),4326) AS geom)
            SELECT ST_IsValid(geom) AND NOT ST_IsEmpty(geom),
                   ST_Covers(geom, ST_SetSRID(ST_MakePoint(%s,%s),4326)) FROM boundary
        ''', (json.dumps(self.geometry), query.longitude, query.latitude)).fetchone()
        if not value[0]:
            raise CoverageUnavailable('Invalid configured coverage geometry')
        if not value[1]:
            raise OutsideCoverage('Coordinates are outside the configured Yerevan coverage')
