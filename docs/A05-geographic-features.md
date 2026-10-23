# A05 geographic data and proximity features

## Districts and unresolved data

The district registry uses the 12 administrative districts named by the
[Yerevan Municipality](https://www.yerevan.am/en/administrative-districts/).
English and Armenian aliases normalize to stable IDs (`ajapnyak`, `arabkir`,
`kanaker-zeytun`, etc.). The parser accepts only an explicit district field or
structured address property that exactly matches a registry alias. It does not
guess a district from a listing title or prose. Unknown source values remain
unmapped (`district_id = null`, `district_status = unresolved`). Raw source
records are retained in `listings.raw_data`; `properties.district_source`
records the field's origin.

Administrative district polygons are not included in this revision. Therefore
coordinates alone do not cause a district assignment. Add a reviewed municipal
boundary dataset and a point-in-polygon check before enabling that inference.

## Listing coordinate provenance

`properties.geom` remains a nullable WGS84 (`SRID 4326`) point. `coordinate_source`
records the extraction method; `coordinate_confidence` is `exact`, `approximate`,
or `unknown`. Coordinates extracted from list.am map attributes, inline data,
or map links are labeled approximate because the source may provide a generalized
pin rather than a surveyed building entrance. Missing or unprovenanced imported
coordinates remain unknown. Listings without a valid coordinate are retained;
their `geo_status` is unresolved and proximity distances are null.

The migration marks pre-A05 points `approximate` with source
`list.am:legacy-coordinate-provenance-unrecorded`, reflecting the existing
ingestion documentation while disclosing that the exact extraction field was
not retained historically.

## Reference points and distance definition

`data_pipeline/geography.py` contains the versioned `yerevan-geo-v1` reference set.
`geographic_reference_points` stores each point's coordinates, source URL,
coordinate confidence, kind, and registry version after the enrichment command runs.

- Ten Yerevan Metro stations, matching the [Municipality's station roster](https://www.yerevan.am/en/metro/).
  Station point coordinates are approximate and sourced from the
  [Citylines Yerevan station dataset](https://cdn.citylines.co/api/yerevan/raw_source/stations).
- Four main-campus points (YSU, National Polytechnic University, Yerevan State
  Medical University, and American University of Armenia). These are a starter
  set, not a complete census. Institution addresses/point references are linked
  beside each record in the registry.
- City center is defined as the Republic Square central reference point
  (`40.17767, 44.51562`), aligned approximately with the Republic Square Metro
  station point. It is one documented anchor, not a claim that every use of
  “city center” means the entire Kentron district.

`distance_metro_m`, `distance_university_m`, and `distance_center_m` are
great-circle surface distances calculated with the Haversine formula and mean
Earth radius 6,371,008.8 m. They are straight-line distances, not walking or
driving routes. The nearest station/campus stable IDs accompany the first two
values. Distances are rounded to 0.1 m for a stable payload; given the input
point confidence, that decimal precision is representational and does not imply
survey-grade accuracy. Features include `geo_status` and `geography_version`.

## Consumers and checks

The ingestion pipeline computes and stores these fields on `properties`. The
`property_geographic_features` PostgreSQL view exposes them by `property_id` as
the handoff interface for ML and API consumers; those consumers can join the
view to listings without changing the source listing schema. After migration,
seed the reference registry and recompute existing rows with
`python -m data_pipeline.enrich_geography`.
Dataset and reference-set changes require a `GEOGRAPHY_VERSION` bump so
consumers can reproduce feature generation.

Known-reference checks cover the Republic Square center, a metro station's
zero self-distance, a university-nearby Yerevan point, Armenian/English district
aliases, and missing/out-of-range coordinates. Unknown values remain null; no
`99999` sentinel is used.

## Source and coverage limitations

The Municipality is authoritative for district names and Metro station count,
but the municipality page does not publish station coordinate files. Metro
coordinates are consequently labeled approximate and have an explicit source
URL. University coordinates are campus/place markers, not all faculty or
campus entrances. Confirm source licensing and refresh/version dates before
using this starter reference dataset for a public operational valuation. The
feature schema and provenance fields support replacing or extending the registry
without changing source listing tables.
