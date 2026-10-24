```powershell
$env:DATABASE_URL = "postgresql+psycopg://USER:PASSWORD@localhost:5432/fairrent_dev"
.venv\Scripts\python.exe -m data_pipeline.export_dataset `
  --as-of 2026-10-24 --version v1.0.0
```

Use the actual snapshot date and your local database credentials. Do not paste credentials into source files or
commit them. The exporter reads only listings observed before the end of `--as-of` (UTC) and writes to
`data/processed/v1.0.0/`, which is ignored by Git. Generated CSVs and reports should not be committed.

An existing version is immutable: rerunning the same inputs returns the existing directory if its content hash
matches. If the same version label would produce different content, export under a new version label.

## Snapshot and leakage policy

Each row is the latest listing state recorded by `last_seen_at` on or before the requested date. Its
`observation_date` and `observation_at` identify that source observation; `price_usd` is monthly asking rent.
Inactive listings are retained when they have a valid observation before the cutoff. This is a cross-sectional
snapshot of each listing's latest observed state, not one row per historical price change. The database records
price changes but does not preserve a full feature snapshot for every historical price event; exporting old prices
with today's mutable listing features would leak future information, so those events are not used as training rows.

The exporter requires a valid positive USD target, a valid coordinate pair, and a supported long-term rental period,
following the B02 training record requirements. Daily and weekly rentals are excluded even though ingestion keeps
their normalized values for provenance. Optional missing fields remain blank/null. It hashes A04 property groups into opaque
`dedup_group_id` values. Groups are sorted by earliest observation date and assigned to chronological 70/15/15
train/validation/test windows. All records for a group stay in one split. Rows observed after their group's split
boundary are excluded. If dates are tied or too few groups exist, split sizes may differ from 70/15/15; exact date
boundaries and realized counts appear in the report and manifest.

## Output files

- `train.csv`, `validation.csv`, `test.csv`: contract features, target, observation dates, hashed duplicate group,
  and conversion/source/geography provenance.
- `manifest.json`: dataset and contract versions, feature definitions and roles, split method and ratios, privacy
  exclusions, source, as-of date, and SHA-256 snapshot checksum.
- `quality_report.json`: input/eligible/excluded counts, invalid values retained in parser trace fields, missingness,
  duplicate counts, neighborhood coverage, split counts/boundaries, and post-boundary exclusions. It also reports
  quarantine event counts from ingestion-run summaries.

Direct listing identifiers, URLs, titles, descriptions, addresses, image URLs, and raw listing data are not exported.
The group key is a SHA-256 pseudonymous identifier derived from the normalized A04 property grouping and a
disambiguator; it contains no source listing ID. Export files are local processed data and must not be committed.

## Reproducibility

The explicit as-of date, immutable version label, deterministic ordering/serialization, and manifest checksum make
repeated exports from unchanged database state byte-for-byte reproducible. Keep the manifest with local model runs
to record which snapshot and feature contract were used.
