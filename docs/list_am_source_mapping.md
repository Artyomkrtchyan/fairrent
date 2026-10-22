# [A01] List.am Source Mapping & Field Analysis

## 1. Available Fields & Missing Values
The parser implementation supports URL identity, title, price text, area, rooms, floor, description, coordinates,
explicit district metadata, explicit address metadata, and OpenGraph/Twitter image metadata. Its selectors are
tested against synthetic fixtures; they have **not** been confirmed against live List.am pages. See the detailed
[source analysis](../data_pipeline/docs/source-analysis.md) for each selector and its verification status.

Building type is not extracted yet. Utilities remain unknown unless the source explicitly states them. Missing
optional values stay null (images use an empty list); the parser does not infer districts or addresses from ad text.
Coordinates may be omitted, rounded, or approximate. Exact address data and interior attributes may be absent.

## 2. Currencies & Rental Periods
* **Currencies:** The source analysis currently identifies USD and AMD as expected source currencies. The parser also recognizes EUR, but that has not been verified against live source pages. Conversion currently uses static configured rates, with rate source/date recorded; it is not a live daily-rate feed.
* **Rental Periods:** The target category is strictly **Long-term Rent** (Armenian: երկարաժամկետ, Russian: долгосрочная аренда), distinguished from daily or short-term vacation rentals.

## 3. Geographic Coordinates & Accuracy
* **Availability:** Exact latitude and longitude coordinates are only occasionally embedded directly via map scripts or DOM data attributes. In many listings, they are completely absent.
* **Accuracy:** When present, they are often coarse or approximate (representing a neighborhood centroid or street block rather than an exact pin). Therefore, the data pipeline and database layer (PostGIS) rely on **geographic enrichment and municipal ontology proximity mapping** (e.g., measuring distance to metro nodes, universities, and city centers) to establish accurate baseline tiers.

## 4. Identification & Duplicate Handling
* **Listing Identification:** Each listing is uniquely identified by its native `external_id` extracted from the URL path (enforced by a unique constraint in PostgreSQL to ensure idempotency during weekly cron sweeps).
* **Duplicate Groups:** Listings are not deleted or merged. The implemented grouping links listings to a shared property only when source, known area, rooms, floor, and coordinate distance satisfy the documented thresholds. Image similarity and repost timing are not part of the current algorithm; see [storage and ingestion](../data_pipeline/docs/storage-and-ingestion.md).

## 5. Synthetic / Sanitized Example Record
```json
{
  "external_id": "19823456",
  "title": "3-room apartment on Aram Street, 85 sq.m., new building",
  "price_usd": 1250.0,
  "price_amd": 481250.0,
  "district": "Kentron",
  "address_raw": "Aram St, Center, Yerevan",
  "area_sqm": 85.0,
  "rooms_count": 3,
  "floor": 5,
  "total_floors": 14,
  "building_type": "new_building",
  "description": "Spacious newly renovated apartment in the heart of Yerevan with modern appliances and central heating.",
  "images": ["[https://img.list.am/s/1/234567.jpg](https://img.list.am/s/1/234567.jpg)"]
}
