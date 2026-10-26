"""Extract the pinned HDX Yerevan boundary without altering its coordinates.

Usage: python infra/valuation-coverage/import_boundary.py path/to/arm_admin_boundaries.geojson.zip
Download SOURCE_URL separately; imports never fetch a mutable remote resource.
"""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

SOURCE_URL = ('https://data.humdata.org/dataset/37b89555-ef3e-4b26-a1ba-070318016853/'
              'resource/000c6626-ea37-4618-b0e4-1e4de7e30902/download/arm_admin_boundaries.geojson.zip')
SOURCE_SHA256 = 'db62f57fcdc8e2082e7b540dabdd23bf80eca209fa43b9ea7e3bf15abef1ae63'


def extract(path):
    if hashlib.sha256(Path(path).read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError('Source checksum changed; review the new dataset before importing')
    with zipfile.ZipFile(path) as archive:
        collection = json.loads(archive.read('arm_admin1.geojson'))
    if collection['crs']['properties']['name'] != 'urn:ogc:def:crs:OGC:1.3:CRS84':
        raise ValueError('Expected WGS84 longitude/latitude coordinates')
    matches = [f for f in collection['features'] if f['properties']['adm1_pcode'] == 'AM01']
    if len(matches) != 1 or matches[0]['properties']['adm1_name'] != 'Yerevan':
        raise ValueError('Expected exactly one Yerevan administrative boundary')
    feature = matches[0]
    if feature['geometry']['type'] not in {'Polygon', 'MultiPolygon'}:
        raise ValueError('Expected polygon geometry')
    feature['id'] = 'AM01'
    feature['properties'].update(
        version='yerevan-hdx-cod-ab-v01-valid-2023-10-02-' + SOURCE_SHA256[:12],
        source='https://data.humdata.org/dataset/cod-ab-arm',
        source_download=SOURCE_URL, source_archive_sha256=SOURCE_SHA256,
        source_member='arm_admin1.geojson', source_dataset_version='v01',
        source_boundary_created='2014-10-01', source_reviewed='2024-01-31',
        retrieved_on='2026-10-23',
        attribution='Government of Armenia (various agencies); quality assured and published by OCHA FIS and HDX',
        license='CC-BY-3.0-IGO', license_url='https://creativecommons.org/licenses/by/3.0/igo/',
        transformation='Selected AM01 from ADM1; geometry and coordinate precision unchanged',
    )
    return feature


if __name__ == '__main__':
    destination = Path(__file__).with_name('coverage-hdx.geojson')
    destination.write_text(json.dumps(extract(sys.argv[1]), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(destination)
