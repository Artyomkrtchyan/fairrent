import fixtures from "../../../contracts/fixtures.json";
import type { components } from "./schema";
import { parseCatalogueSearch, type CatalogueSearch } from "@/lib/catalogue-search";

import { parseMapBounds } from "@/lib/map-bounds";

type Listing = components["schemas"]["Listing"];

function compareNullableNumbers(
  left: number | null,
  right: number | null,
  descending: boolean,
): number {
  // Missing values always appear last.
  if (left === null && right === null) return 0;
  if (left === null) return 1;
  if (right === null) return -1;

  return descending ? right - left : left - right;
}

export function selectListings(listings: readonly Listing[], search: CatalogueSearch) {
  const bounds = parseMapBounds(search.bbox);
  const filtered = listings.filter((listing) => {
    if (bounds) {
      const [west, south, east, north] = bounds;
      const { latitude, longitude } = listing;
      if (
        latitude === null ||
        longitude === null ||
        !Number.isFinite(latitude) ||
        !Number.isFinite(longitude) ||
        longitude < west ||
        longitude > east ||
        latitude < south ||
        latitude > north
      )
        return false;
    }
    if (listing.status !== search.status) return false;

    if (search.district_id !== undefined && listing.district_id !== search.district_id) {
      return false;
    }

    if (search.rooms !== undefined && listing.rooms !== search.rooms) {
      return false;
    }

    const price = listing.price_monthly_normalized;
    const area = listing.area_sqm;

    if (search.price_min !== undefined && (price === null || price < search.price_min)) {
      return false;
    }

    if (search.price_max !== undefined && (price === null || price > search.price_max)) {
      return false;
    }

    if (search.area_min !== undefined && (area === null || area < search.area_min)) {
      return false;
    }

    if (search.area_max !== undefined && (area === null || area > search.area_max)) {
      return false;
    }

    return true;
  });

  filtered.sort((left, right) => {
    let comparison = 0;

    switch (search.sort) {
      case "price_asc":
      case "price_desc":
        comparison = compareNullableNumbers(
          left.price_monthly_normalized,
          right.price_monthly_normalized,
          search.sort === "price_desc",
        );
        break;

      case "area_asc":
      case "area_desc":
        comparison = compareNullableNumbers(
          left.area_sqm,
          right.area_sqm,
          search.sort === "area_desc",
        );
        break;

      case "newest": {
        const leftDate = Date.parse(left.published_at ?? left.first_seen_at);
        const rightDate = Date.parse(right.published_at ?? right.first_seen_at);

        comparison = rightDate - leftDate;
        break;
      }
    }

    return comparison || left.id.localeCompare(right.id);
  });

  const start = (search.page - 1) * search.page_size;

  return {
    items: filtered.slice(start, start + search.page_size),
    total: filtered.length,
    page: search.page,
    page_size: search.page_size,
    has_more: search.page * search.page_size < filtered.length,
  };
}

export function mockListingPage(url: URL) {
  const search = parseCatalogueSearch(Object.fromEntries(url.searchParams));

  const listings = fixtures.listings.value.items as Listing[];

  return {
    ...fixtures.listings.value,
    ...selectListings(listings, search),
  };
}
