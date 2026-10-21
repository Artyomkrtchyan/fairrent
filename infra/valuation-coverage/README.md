# Valuation coverage configuration

Place the authoritative A05 Yerevan GeoJSON polygon in `coverage.geojson`.
This local file is deliberately not supplied or committed: demo geometry must
never become a production city boundary. Compose mounts this directory read-only.

Required structure: a GeoJSON `Feature`, geometry `Polygon` or `MultiPolygon`,
WGS84 longitude/latitude coordinates, and nonempty string properties `version`
and `source` identifying the boundary revision and provenance.

No file or invalid configuration: valuations return 503; listings remain usable.
Outside the configured polygon: valuations return 400 / outside_coverage.
The coverage revision plus content checksum is saved with each estimate.
