import { describe, expect, it } from "vitest";
import type { components } from "@/api/schema";
import { snapshotMapPrices } from "@/lib/map-listing-price-snapshot";
import fixtures from "../../../contracts/fixtures.json";

type Listing = components["schemas"]["Listing"];
const base = fixtures.listings.value.items[0] as Listing;
const make = (id: string, district: string, usd: number | null, sqm: number | null): Listing =>
  ({ ...base, id, district_id: district, price_monthly_normalized: usd, area_sqm: sqm });

describe("map rent-price snapshot fallback", () => {
  it("colors only supported districts using observed rent-per-area medians", () => {
    const records = [
      make("1", "kentron", 500, 50), make("2", "kentron", 600, 60),
      make("3", "kentron", 700, 70), make("4", "kentron", 800, 80),
      make("5", "kentron", 900, 90),
      make("6", "arabkir", 200, 50), make("7", "arabkir", 300, 50),
      make("8", "arabkir", null, 50), make("9", "arabkir", 400, null),
    ];
    const snapshot = snapshotMapPrices(records);
    expect(snapshot.districtPrices).toHaveLength(1);
    expect(snapshot.districtPrices[0]?.districtId).toBe("kentron");
    expect(snapshot.districtPrices[0]?.medianUsdM2).toBe(10);
    expect(snapshot.districtPrices[0]?.areaSampleCount).toBe(5);
    expect(snapshot.min).toBe(10);
    expect(snapshot.max).toBe(10);
  });

  it("does not fabricate values from sparse or invalid listings", () => {
    const snapshot = snapshotMapPrices([
      make("1", "kentron", 500, null), make("2", "kentron", 500, 0),
      make("3", "kentron", 500, -20), make("4", "kentron", null, 50),
    ]);
    expect(snapshot.districtPrices).toEqual([]);
    expect(snapshot.min).toBeNull();
    expect(snapshot.max).toBeNull();
  });

  it("deduplicates repeated listings when group information is provided", () => {
    const duplicate = { ...make("2", "kentron", 1200, 60), dedup_group_id: "shared-property" };
    const entries = [
      { ...make("1", "kentron", 600, 60), dedup_group_id: "shared-property" },
      duplicate,
      make("3", "kentron", 500, 50), make("4", "kentron", 500, 50),
      make("5", "kentron", 500, 50), make("6", "kentron", 500, 50),
    ];
    expect(snapshotMapPrices(entries).districtPrices[0]?.areaSampleCount).toBe(5);
  });
});
