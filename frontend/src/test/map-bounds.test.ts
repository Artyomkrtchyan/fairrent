import { describe, expect, it } from "vitest";
import { parseMapBounds, serializeMapBounds } from "@/lib/map-bounds";
import { parseCatalogueSearch } from "@/lib/catalogue-search";
import { selectListings } from "@/api/mock-listings";
import fixtures from "../../../contracts/fixtures.json";
import type { MapListing } from "@/lib/map-listings";

describe("bounded map search", () => {
  it("preserves a valid bbox in URL state alongside the other filters", () => {
    const search = parseCatalogueSearch({ bbox: "44.50,40.10,44.60,40.20", rooms: 2, page: 3 });
    expect(search.bbox).toBe("44.5,40.1,44.6,40.2");
    expect(search.rooms).toBe(2);
    expect(search.page).toBe(3);
    expect(serializeMapBounds([44.50000001, 40.10000001, 44.6, 40.2])).toBe(search.bbox);
  });
  it.each([
    "bad",
    "44,40,45,41",
    "45,40,44,40.1",
    "44,40,44,40.1",
    "181,40,181.1,40.1",
    "44,91,44.1,91.1",
    "44,40,44.1,40.1,99",
    "NaN,40,44,41",
    "170,40,-170,40.1",
  ])("rejects invalid or oversized bounds: %s", (bbox) => {
    expect(parseMapBounds(bbox)).toBeUndefined();
    expect(parseCatalogueSearch({ bbox }).bbox).toBeUndefined();
  });
  it("filters by inclusive coordinates AND existing filters before pagination", () => {
    const base = fixtures.listings.value.items[0] as MapListing;
    const source = [
      { ...base, id: "a", longitude: 44.5, latitude: 40.1, rooms: 2 },
      { ...base, id: "b", longitude: 44.6, latitude: 40.2, rooms: 2 },
      { ...base, id: "c", longitude: 44.7, latitude: 40.2, rooms: 2 },
      { ...base, id: "d", longitude: null, latitude: null, rooms: 2 },
      { ...base, id: "e", longitude: 44.55, latitude: 40.15, rooms: 3 },
    ];
    const search = parseCatalogueSearch({ bbox: "44.5,40.1,44.6,40.2", rooms: 2, page_size: 1 });
    const first = selectListings(source, search);
    expect(first.items.map((listing) => listing.id)).toEqual(["a"]);
    expect(first.total).toBe(2);
    expect(first.has_more).toBe(true);
    expect(selectListings(source, { ...search, page: 2 }).items[0]?.id).toBe("b");
    expect(selectListings(source, parseCatalogueSearch({})).total).toBe(5);
  });
});
