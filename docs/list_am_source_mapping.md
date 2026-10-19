# [A01] List.am Source Mapping & Field Analysis

## 1. Available Fields & Missing Values
* **Core Fields Collected:** 
  * Listing ID / External URL hash (`external_id`)
  * Title / Header description (`title`)
  * Price in original currency and normalized USD/AMD (`price_usd`, `price_amd`)
  * Location details: Administrative district, raw address string (`district`, `address_raw`)
  * Property parameters: Area in square meters (`area_sqm`), room count (`rooms_count`), floor and total building floors (`floor`, `total_floors`), building type (`building_type`)
  * Full description text block (`description`)
  * Image URLs gallery (`images`)
* **Frequently Missing or Optional Fields:**
  * Exact street numbers or building numbers (often generalized by landlords to street names only).
  * Precise geospatial coordinates (lat/long markers are frequently omitted or generalized).
  * Specific interior attributes (ceiling heights, exact balcony types, precise renovation year).

## 2. Currencies & Rental Periods
* **Currencies:** Prices appear in **USD ($)** and **Armenian Drams (AMD / ֏)**. The pipeline normalizes these into a standard base currency (USD) using daily exchange rate mappings.
* **Rental Periods:** The target category is strictly **Long-term Rent** (Armenian: երկարաժամկետ, Russian: долгосрочная аренда), distinguished from daily or short-term vacation rentals.

## 3. Geographic Coordinates & Accuracy
* **Availability:** Exact latitude and longitude coordinates are only occasionally embedded directly via map scripts or DOM data attributes. In many listings, they are completely absent.
* **Accuracy:** When present, they are often coarse or approximate (representing a neighborhood centroid or street block rather than an exact pin). Therefore, the data pipeline and database layer (PostGIS) rely on **geographic enrichment and municipal ontology proximity mapping** (e.g., measuring distance to metro nodes, universities, and city centers) to establish accurate baseline tiers.

## 4. Identification & Duplicate Handling
* **Listing Identification:** Each listing is uniquely identified by its native `external_id` extracted from the URL path (enforced by a unique constraint in PostgreSQL to ensure idempotency during weekly cron sweeps).
* **Duplicate Groups:** Deduplication logic flags and merges reposted or duplicate listings by evaluating fuzzy matches across key attributes: matching area ($\text{m}^2$), rooms, district, building type, and identical or heavily overlapping image URLs/hashes posted within short time windows.

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