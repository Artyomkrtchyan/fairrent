import { describe, expect, it } from "vitest";
import fixtures from "../../../contracts/fixtures.json";
import { hasMapCoordinates, type MapListing } from "@/lib/map-listings";

const listing = fixtures.listings.value.items[0] as MapListing;

describe("rental marker coordinates", () => {
  it("accepts source-reported exact and approximate coordinates", () => {
    for (const confidence of ["exact", "approximate"] as const) {
      expect(
        hasMapCoordinates({
          ...listing,
          latitude: 40.18,
          longitude: 44.51,
          coordinate_confidence: confidence,
        }),
      ).toBe(true);
    }
  });
  it.each([
    { latitude: null },
    { longitude: null },
    { latitude: NaN },
    { longitude: Infinity },
    { latitude: 91 },
    { longitude: -181 },
    { coordinate_confidence: "unknown" as const },
  ])("does not invent a marker for unusable coordinates: %j", (overrides) => {
    expect(
      hasMapCoordinates({
        ...listing,
        latitude: 40.18,
        longitude: 44.51,
        coordinate_confidence: "approximate",
        ...overrides,
      }),
    ).toBe(false);
  });
});
