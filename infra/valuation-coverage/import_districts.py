"""Normalize the pinned municipal GIS export; never alter polygon coordinates."""
import hashlib
import json
from pathlib import Path
import sys

SOURCE = 'https://gis.yerevan.am/server/rest/services/Hosted/Yerevan_Districts/FeatureServer/0'
SOURCE_SHA256 = '017596a12ec98bb1bc03d813da2dc919ac51a48786c7b59e8f909d3c179f4d4d'
DISTRICTS = {
    '01-001': ('ajapnyak', 'Ajapnyak'), '01-002': ('avan', 'Avan'),
    '01-003': ('arabkir', 'Arabkir'), '01-004': ('davtashen', 'Davtashen'),
    '01-005': ('erebuni', 'Erebuni'), '01-006': ('kentron', 'Kentron'),
    '01-007': ('malatia-sebastia', 'Malatia-Sebastia'), '01-008': ('nor-nork', 'Nor Nork'),
    '01-009': ('nork-marash', 'Nork-Marash'), '01-010': ('nubarashen', 'Nubarashen'),
    '01-011': ('shengavit', 'Shengavit'), '01-012': ('kanaker-zeytun', 'Kanaker-Zeytun'),
}


def extract(path):
    raw = Path(path).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != SOURCE_SHA256:
        raise ValueError('Source export changed; review the snapshot before updating the pin')
    data = json.loads(raw.decode('utf-8-sig'))
    if data.get('type') != 'FeatureCollection' or len(data['features']) != 12:
        raise ValueError('Expected exactly 12 municipal district polygons')
    codes = [f['properties']['community_code'] for f in data['features']]
    if set(codes) != set(DISTRICTS) or len(set(codes)) != 12:
        raise ValueError('District codes differ from the reviewed municipal registry')
    for feature in data['features']:
        props = feature['properties']
        district_id, name = DISTRICTS[props['community_code']]
        if feature['geometry']['type'] not in {'Polygon', 'MultiPolygon'}:
            raise ValueError('Expected polygon geometry')
        feature['id'] = district_id
        feature['properties'] = dict(district_id=district_id, name=name,
            name_hy=props['settlement_name'], community_code=props['community_code'])
    data['features'].sort(key=lambda f: f['id'])
    return dict(type='FeatureCollection', properties=dict(
        version='yerevan-municipal-districts-2026-10-23-' + digest[:12],
        source=SOURCE, source_export_sha256=digest, retrieved_on='2026-10-23',
        attribution='Yerevan Municipality, public GIS, Yerevan Districts layer',
        license='Not specified by the municipal GIS item; no open license is asserted',
        source_item='https://gis.yerevan.am/portal/home/item.html?id=a6d8fac221e3492593303f6b2074101a',
        transformation='Server export outSR=4326; mapped community codes to A05 IDs; geometry unchanged'),
        features=data['features'])


if __name__ == '__main__':
    target = Path(__file__).with_name('districts.geojson')
    target.write_text(json.dumps(extract(sys.argv[1]), ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    print(target)
