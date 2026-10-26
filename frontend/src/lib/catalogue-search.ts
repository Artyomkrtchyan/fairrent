import type { ListingQuery } from "@/api/listings";

import { parseMapBounds, serializeMapBounds } from "./map-bounds";

const SORT_OPTIONS = ["newest", "price_asc", "price_desc", "area_asc", "area_desc"] as const;

export type CatalogueSort = (typeof SORT_OPTIONS)[number];

export type CatalogueSearch = Pick<
  ListingQuery,
  "bbox" | "district_id" | "price_min" | "price_max" | "rooms" | "area_min" | "area_max"
> & {
  page: number;
  page_size: number;
  sort: CatalogueSort;
  status: "active" | "inactive";
};

function numeric(value: unknown): number | undefined {
  if (typeof value !== "number" && typeof value !== "string") {
    return undefined;
  }

  if (typeof value === "string" && value.trim() === "") {
    return undefined;
  }

  const result = Number(value);

  return Number.isFinite(result) ? result : undefined;
}

function positiveInteger(
  value: unknown,
  fallback: number,
  maximum = Number.MAX_SAFE_INTEGER,
): number {
  const result = numeric(value);

  return result !== undefined && Number.isSafeInteger(result) && result >= 1 && result <= maximum
    ? result
    : fallback;
}

function isSort(value: unknown): value is CatalogueSort {
  return SORT_OPTIONS.some((option) => option === value);
}

export function parseCatalogueSearch(raw: Record<string, unknown>): CatalogueSearch {
  const result: CatalogueSearch = {
    page: positiveInteger(raw["page"], 1),
    page_size: positiveInteger(raw["page_size"], 20, 100),
    sort: isSort(raw["sort"]) ? raw["sort"] : "newest",
    status: raw["status"] === "inactive" ? "inactive" : "active",
  };

  const bounds = parseMapBounds(raw["bbox"]);
  if (bounds) result.bbox = serializeMapBounds(bounds);

  const district = raw["district_id"];

  if (typeof district === "string" && district.trim()) {
    result.district_id = district.trim();
  }

  const rooms = numeric(raw["rooms"]);

  if (rooms !== undefined && Number.isSafeInteger(rooms) && rooms >= 1) {
    result.rooms = rooms;
  }

  const priceMin = numeric(raw["price_min"]);
  const priceMax = numeric(raw["price_max"]);

  if (priceMin !== undefined && priceMin >= 0) {
    result.price_min = priceMin;
  }

  if (priceMax !== undefined && priceMax >= 0) {
    result.price_max = priceMax;
  }

  const areaMin = numeric(raw["area_min"]);
  const areaMax = numeric(raw["area_max"]);

  if (areaMin !== undefined && areaMin > 0) {
    result.area_min = areaMin;
  }

  if (areaMax !== undefined && areaMax > 0) {
    result.area_max = areaMax;
  }

  if (
    result.price_min !== undefined &&
    result.price_max !== undefined &&
    result.price_min > result.price_max
  ) {
    delete result.price_min;
    delete result.price_max;
  }

  if (
    result.area_min !== undefined &&
    result.area_max !== undefined &&
    result.area_min > result.area_max
  ) {
    delete result.area_min;
    delete result.area_max;
  }

  return result;
}
