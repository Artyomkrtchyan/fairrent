import { describe, expect, it } from "vitest";
import fixtures from "../../../contracts/fixtures.json";
import type { components } from "@/api/schema";
import { selectListings } from "@/api/mock-listings";
import { parseCatalogueSearch } from "@/lib/catalogue-search";

type Listing = components["schemas"]["Listing"];

const base = fixtures.listings.value.items[0] as Listing;

function apartment(number: number, changes: Partial<Listing> = {}): Listing {
  return {
    ...base,
    id: `00000000-0000-4000-8000-${String(number).padStart(12, "0")}`,
    ...changes,
  };
}

const listings: Listing[] = [
  apartment(1, {
    district_id: "kentron",
    rooms: 2,
    price_monthly_normalized: 600,
    area_sqm: 50,
  }),
  apartment(2, {
    district_id: "arabkir",
    rooms: 3,
    price_monthly_normalized: 900,
    area_sqm: 80,
  }),
  apartment(3, {
    district_id: "kentron",
    rooms: 2,
    price_monthly_normalized: 400,
    area_sqm: 35,
  }),
];

describe("mock catalogue results", () => {
  it("combines filters and includes exact range boundaries", () => {
    const result = selectListings(
      listings,
      parseCatalogueSearch({
        district_id: "kentron",
        rooms: 2,
        price_min: 600,
        price_max: 600,
        area_min: 50,
        area_max: 50,
      }),
    );

    expect(result.items.map((item) => item.id)).toEqual([listings[0]!.id]);
    expect(result.total).toBe(1);
  });

  it("matches the exact room count, not four or more", () => {
    const source = [apartment(1, { rooms: 4 }), apartment(2, { rooms: 5 })];

    const result = selectListings(source, parseCatalogueSearch({ rooms: 4 }));

    expect(result.items.map((item) => item.rooms)).toEqual([4]);
  });

  it("returns an empty page when nothing matches", () => {
    const result = selectListings(listings, parseCatalogueSearch({ price_max: 100 }));

    expect(result.items).toEqual([]);
    expect(result.total).toBe(0);
    expect(result.has_more).toBe(false);
  });

  it("excludes unknown values when a numeric filter is applied", () => {
    const source = [
      apartment(1, {
        price_monthly_normalized: null,
        area_sqm: null,
      }),
    ];

    expect(selectListings(source, parseCatalogueSearch({ price_max: 1000 })).items).toEqual([]);

    expect(selectListings(source, parseCatalogueSearch({ area_min: 1 })).items).toEqual([]);
  });

  it.each([
    ["price_asc", [400, 600, 900]],
    ["price_desc", [900, 600, 400]],
  ])("sorts rent with %s", (sort, expected) => {
    const result = selectListings(listings, parseCatalogueSearch({ sort }));

    expect(result.items.map((item) => item.price_monthly_normalized)).toEqual(expected);
  });

  it.each([
    ["area_asc", [35, 50, 80]],
    ["area_desc", [80, 50, 35]],
  ])("sorts area with %s", (sort, expected) => {
    const result = selectListings(listings, parseCatalogueSearch({ sort }));

    expect(result.items.map((item) => item.area_sqm)).toEqual(expected);
  });

  it.each(["price_asc", "price_desc", "area_asc", "area_desc"])(
    "keeps missing values last with %s",
    (sort) => {
      const source = [
        apartment(1, {
          price_monthly_normalized: null,
          area_sqm: null,
        }),
        apartment(2, {
          price_monthly_normalized: 600,
          area_sqm: 50,
        }),
      ];

      const result = selectListings(source, parseCatalogueSearch({ sort }));

      expect(result.items.map((item) => item.id)).toEqual([source[1]!.id, source[0]!.id]);
    },
  );

  it("uses first-seen time when publication time is missing", () => {
    const source = [
      apartment(1, {
        published_at: null,
        first_seen_at: "2026-10-01T00:00:00Z",
      }),
      apartment(2, {
        published_at: "2026-10-20T00:00:00Z",
        first_seen_at: "2026-10-21T00:00:00Z",
      }),
      apartment(3, {
        published_at: null,
        first_seen_at: "2026-10-21T00:00:00Z",
      }),
    ];

    const result = selectListings(source, parseCatalogueSearch({ sort: "newest" }));

    expect(result.items.map((item) => item.id)).toEqual([
      source[2]!.id,
      source[1]!.id,
      source[0]!.id,
    ]);
  });

  it("breaks sorting ties by ID without changing the source array", () => {
    const source = [
      apartment(2, { price_monthly_normalized: 600 }),
      apartment(1, { price_monthly_normalized: 600 }),
    ];

    const originalOrder = source.map((item) => item.id);

    const result = selectListings(source, parseCatalogueSearch({ sort: "price_asc" }));

    expect(result.items.map((item) => item.id)).toEqual([source[1]!.id, source[0]!.id]);
    expect(source.map((item) => item.id)).toEqual(originalOrder);
  });

  it("filters and sorts before selecting a page", () => {
    const result = selectListings(
      listings,
      parseCatalogueSearch({
        district_id: "kentron",
        sort: "price_asc",
        page: 2,
        page_size: 1,
      }),
    );

    expect(result.items.map((item) => item.price_monthly_normalized)).toEqual([600]);
    expect(result.total).toBe(2);
    expect(result.page).toBe(2);
    expect(result.has_more).toBe(false);
  });

  it("reports more results when another page exists", () => {
    const result = selectListings(listings, parseCatalogueSearch({ page: 1, page_size: 1 }));

    expect(result.items).toHaveLength(1);
    expect(result.total).toBe(3);
    expect(result.has_more).toBe(true);
  });

  it("returns an empty out-of-range page without losing the total", () => {
    const result = selectListings(listings, parseCatalogueSearch({ page: 10, page_size: 1 }));

    expect(result.items).toEqual([]);
    expect(result.total).toBe(3);
    expect(result.has_more).toBe(false);
  });

  it("shows active listings by default and inactive ones on request", () => {
    const source = [apartment(1, { status: "active" }), apartment(2, { status: "inactive" })];

    expect(
      selectListings(source, parseCatalogueSearch({})).items.map((item) => item.status),
    ).toEqual(["active"]);

    expect(
      selectListings(source, parseCatalogueSearch({ status: "inactive" })).items.map(
        (item) => item.status,
      ),
    ).toEqual(["inactive"]);
  });
});
