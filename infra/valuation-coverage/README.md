# Valuation geography

`districts.geojson` contains all 12 administrative district polygons from the
public [Yerevan Municipality GIS district layer](https://gis.yerevan.am/server/rest/services/Hosted/Yerevan_Districts/FeatureServer/0).
Municipal community codes map to stable A05 district IDs. Canonical English
labels accompany the source Armenian names. The server exports WGS84 longitude/
latitude coordinates with `outSR=4326`; no local rounding or simplification occurs.
Original custom ARM_PCS projection and edit metadata are retained in
`districts-source-layer.json`; portal metadata is in `districts-source-item.json`.
Retrieved 2026-10-23; the portal edit timestamp is not a legal effective date or
a guarantee of survey accuracy.

`coverage.geojson` is a GeoJSON Feature/MultiPolygon built by taking the geometric
union of those same 12 polygons. It defines operational valuation coverage, not
a new legal boundary determination or a guarantee of enough comparables. This
keeps city eligibility and district lookup on one source snapshot. Disconnected
components are preserved; no buffering, snapping or convex hull fills gaps.

## Attribution and terms

Attribution: Yerevan Municipality, public GIS, Yerevan Districts layer.
The [portal item](https://gis.yerevan.am/portal/home/item.html?id=a6d8fac221e3492593303f6b2074101a)
is public but its `licenseInfo` and attribution fields are empty. No open reuse/
redistribution license is asserted for municipal polygons or their derived union.
Confirm municipal reuse terms before public redistribution and retain attribution.

The separate `coverage-hdx.geojson` is a reference/comparison artifact, not the
default runtime boundary. It comes from Government of Armenia data published
and quality assured by OCHA FIS and [HDX COD-AB](https://data.humdata.org/dataset/cod-ab-arm),
under [CC BY 3.0 IGO](https://creativecommons.org/licenses/by/3.0/igo/).
HDX identifies v01, boundaries created/edited 2014-10-01, valid-on 2023-10-02 and
reviewed 2024-01-31. Metadata is in `source-metadata.json`. That license applies
only to HDX data. Its older extent differs from the municipal district union;
it is not mixed with or used to clip the current district polygons.

## Reproduction

Download the municipal export from the layer URL plus
`/query?where=1%3D1&outFields=*&outSR=4326&f=geojson` and save the raw response.
Then run:

```bash
python infra/valuation-coverage/import_districts.py /path/to/export.geojson
# Build-time dependency only; API runtime continues using PostGIS.
python -m pip install Shapely==2.2.0
python infra/valuation-coverage/build_coverage.py
```

The importer verifies the pinned source SHA-256 and exactly 12 expected community
codes. Changed input requires source review and a new pin/version. The union
stores a SHA-256 of canonical JSON (sorted keys, compact separators, UTF-8,
unescaped Unicode, finite numbers only), so LF/CRLF and indentation do not alter
the district snapshot checksum. The algorithm is recorded in the Feature.
City and district versions
plus content checksums are recorded with each estimate.

To reproduce the older HDX comparison file, download `source_download` from its
Feature properties and run
`python infra/valuation-coverage/import_boundary.py /path/to/arm_admin_boundaries.geojson.zip`.
That importer also verifies its source archive pin.

## Runtime behavior

Compose mounts this directory read-only and sets:

```text
VALUATION_COVERAGE_FILE=/coverage/coverage.geojson
VALUATION_DISTRICTS_FILE=/coverage/districts.geojson
```

Outside Compose, set both variables to absolute local paths. No download or
Shapely dependency is needed at startup. Coverage expects a GeoJSON Feature,
Polygon/MultiPolygon geometry, and nonempty `properties.version` and `source`.
Missing/invalid configured geography returns 503; listings remain usable.
Coordinates outside the city union return 400/outside_coverage.

PostGIS resolves the subject and candidates in a batch. One `ST_Covers` match
supplies the canonical district label to ML. Shared borders, overlaps and gaps
remain unknown; no nearest-district guess is made. A uniquely resolved subject
restricts both statistics and prediction to the same district plus the existing
radius, rooms and time filters. An unresolved subject uses a disclosed radius-only
cohort. If district configuration is deliberately omitted, radius-only mode
also discloses that polygons are not configured. Invalid configured data never
silently disables district lookup. Source property/listing rows are not rewritten.
