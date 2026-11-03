"""Resolve coordinates against a versioned district polygon snapshot in PostGIS."""
from hashlib import sha256
import json
from pathlib import Path

try:
    from .valuation_coverage import CoverageUnavailable
    from .geographic_features import DISTRICTS
except ImportError:
    from valuation_coverage import CoverageUnavailable
    from geographic_features import DISTRICTS

DISTRICT_IDS = frozenset(DISTRICTS)


class DistrictRegistry:
    def __init__(self, path):
        try:
            data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
            props = data['properties']
            features = data['features']
            ids = [f['properties']['district_id'] for f in features]
            if (data['type'] != 'FeatureCollection' or len(ids) != 12
                    or set(ids) != DISTRICT_IDS
                    or not isinstance(props['version'], str) or not props['version'].strip()
                    or not isinstance(props['source'], str) or not props['source'].strip()):
                raise ValueError('Invalid district registry')
            for feature in features:
                if (feature['geometry']['type'] not in {'Polygon', 'MultiPolygon'}
                        or not isinstance(feature['properties']['name'], str)
                        or feature['properties']['name'] != DISTRICTS[feature['properties']['district_id']][0]):
                    raise ValueError('Invalid district feature')
            self.features = features
            self.version = props['version'] + ':' + sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
        except (OSError, KeyError, TypeError, ValueError) as exc:
            raise CoverageUnavailable('District boundary registry is not configured correctly') from exc

    def resolve_many(self, connection, points):
        """Return (slug, canonical label) or None, preserving input order.

        Shared boundary points, gaps and overlaps remain unresolved. No nearest-district
        fallback or coordinate perturbation is allowed. All geometry operations
        occur inside the caller's transaction and statement timeout.
        """
        if not points:
            return []
        geometries = connection.execute('''
            WITH districts AS MATERIALIZED (
                SELECT f->'properties'->>'district_id' AS id,
                       f->'properties'->>'name' AS name,
                       ST_SetSRID(ST_GeomFromGeoJSON((f->'geometry')::text),4326) AS geom
                FROM jsonb_array_elements(%s::jsonb) f
            )
            SELECT bool_and(ST_IsValid(geom) AND NOT ST_IsEmpty(geom)) FROM districts
        ''', (json.dumps(self.features),)).fetchone()
        if not geometries[0]:
            raise CoverageUnavailable('Invalid district boundary geometry')
        rows = connection.execute('''
            WITH districts AS MATERIALIZED (
                SELECT f->'properties'->>'district_id' AS id,
                       f->'properties'->>'name' AS name,
                       ST_SetSRID(ST_GeomFromGeoJSON((f->'geometry')::text),4326) AS geom
                FROM jsonb_array_elements(%s::jsonb) f
            ), points AS (
                SELECT ordinal, ST_SetSRID(ST_MakePoint((p->>1)::float8,(p->>0)::float8),4326) AS geom
                FROM jsonb_array_elements(%s::jsonb) WITH ORDINALITY AS t(p,ordinal)
            )
            SELECT p.ordinal, CASE WHEN count(d.id)=1 THEN min(d.id) END,
                   CASE WHEN count(d.id)=1 THEN min(d.name) END
            FROM points p LEFT JOIN districts d ON ST_Covers(d.geom,p.geom)
            GROUP BY p.ordinal ORDER BY p.ordinal
        ''', (json.dumps(self.features), json.dumps(points))).fetchall()
        return [(row[1], row[2]) if row[1] else None for row in rows]
