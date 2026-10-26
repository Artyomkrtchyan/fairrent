"""Build operational city coverage from the same reviewed district snapshot.

Authoring dependency: Shapely 2.2.0. Not required by the API runtime.
"""
from hashlib import sha256
import json
from pathlib import Path

from shapely.geometry import mapping, shape
from shapely.ops import unary_union


def build(path):
    raw = Path(path).read_bytes()
    districts = json.loads(raw.decode('utf-8'))
    # Git normalizes text to LF; Windows authoring can leave CRLF in the
    # working copy. Fingerprint JSON content, not platform-specific bytes.
    snapshot = json.dumps(districts, sort_keys=True, separators=(',', ':'),
                          ensure_ascii=False, allow_nan=False).encode('utf-8')
    geometries = [shape(f['geometry']) for f in districts['features']]
    if len(geometries) != 12 or not all(g.is_valid and not g.is_empty for g in geometries):
        raise ValueError('Expected 12 valid nonempty district polygons')
    union = unary_union(geometries)
    if not union.is_valid or union.geom_type not in {'Polygon', 'MultiPolygon'}:
        raise ValueError('Invalid district union')
    props = districts['properties']
    return dict(type='Feature', id='AM01', properties=dict(
        name='Yerevan', version=props['version'] + '-union-v1', source=props['source'],
        attribution=props['attribution'], license=props['license'],
        retrieved_on=props['retrieved_on'], district_snapshot_sha256=sha256(snapshot).hexdigest(),
        district_snapshot_hash_algorithm='sha256-canonical-json-v1',
        source_export_sha256=props['source_export_sha256'],
        transformation='GEOS unary union of the 12 municipal district polygons; no buffer, snapping or simplification'),
        geometry=mapping(union))


if __name__ == '__main__':
    folder = Path(__file__).parent
    (folder / 'coverage.geojson').write_text(
        json.dumps(build(folder / 'districts.geojson'), ensure_ascii=False, separators=(',', ':')) + '\n',
        encoding='utf-8')
