import { describe, expect, it } from "vitest";
import type { SnapshotListing } from "@/lib/listing-snapshot";
import { buildDistrictSnapshot, median, snapshotMedian, uniqueActiveListings } from "@/lib/listing-snapshot";
import fixtures from "../../../contracts/fixtures.json";

const base = fixtures.listings.value.items[0] as SnapshotListing;

function listing(id: string, district: string | null, rent: number | null, area: number | null, extra: Partial<SnapshotListing> = {}): SnapshotListing {
  return { ...base, id, district_id: district, price_monthly_normalized: rent, area_sqm: area, ...extra };
}

describe("listing-based market snapshot", () => {
  it("calculates medians without turning missing prices into zero", () => {
    expect(median([])).toBeNull();
    expect(median([200, 400, 100])).toBe(200);
    expect(median([200, 600, 400, 100])).toBe(300);
    const rows = [
      listing("a", "kentron", 500, 50),
      listing("b", "kentron", 700, 70),
      listing("c", "arabkir", null, null),
      listing("d", "arabkir", 500, 0),
    ];
    const groups = buildDistrictSnapshot(rows);
    const kentron = groups.find((group) => group.districtId === "kentron")!;
    const arabkir = groups.find((group) => group.districtId === "arabkir")!;
    expect(kentron.medianMonthlyUsd).toBe(600);
    expect(kentron.medianPerSqmUsd).toBe(10);
    expect(kentron.pricedCount).toBe(2);
    expect(arabkir.medianMonthlyUsd).toBe(500);
    expect(arabkir.medianPerSqmUsd).toBeNull();
    expect(arabkir.areaPricedCount).toBe(0);
    expect(snapshotMedian(rows, "m2")).toBe(10);
  });

  it("deduplicates by known property or group and excludes inactive rows", () => {
    const rows = [
      listing("one", "kentron", 350, 50, { property_id: "same-property", last_seen_at: "2026-10-01T00:00:00Z" }),
      listing("two", "kentron", 650, 50, { property_id: "same-property", last_seen_at: "2026-10-02T00:00:00Z" }),
      listing("three", "kentron", 800, 80, { status: "inactive" }),
    ];
    expect(uniqueActiveListings(rows).map((row) => row.id)).toEqual(["two"]);
    expect(snapshotMedian(rows, "month")).toBe(650);
    expect(buildDistrictSnapshot(rows)[0]?.listingCount).toBe(1);
  });

  it("omits unknown districts from comparisons but keeps them in overall sample", () => {
    const rows = [
      listing("first", null, 800, 40),
      listing("second", "kentron", 400, 40),
    ];
    expect(snapshotMedian(rows, "month")).toBe(600);
    expect(buildDistrictSnapshot(rows).map((row) => row.districtId)).toEqual(["kentron"]);
  });
});
