import { describe, expect, it } from "vitest";
import {
  createBuildingRentSampler,
  footprintCenter,
  rentGradientColor,
} from "@/lib/map-building-rent-colors";
import type { DistrictPrice } from "@/lib/district-price-layer";

describe("building-only rental heatmap", () => {
  it("uses the existing vivid green-yellow-red palette", () => {
    expect(rentGradientColor(0)).toBe("#22c55e");
    expect(rentGradientColor(0.5)).toBe("#facc15");
    expect(rentGradientColor(1)).toBe("#ef4444");
  });

  it("samples only buildings inside supported city polygons", () => {
    const features = [
      {
        properties: { district_id: "test" },
        geometry: {
          type: "Polygon" as const,
          coordinates: [[[44.4, 40.1], [44.6, 40.1], [44.6, 40.3], [44.4, 40.3], [44.4, 40.1]]],
        },
      },
    ];
    const prices = new Map<string, DistrictPrice>([[
      "test",
      { districtId: "test", medianUsdM2: 12, areaSampleCount: 5, periodStart: "2026-11-01", periodEnd: "2026-11-07", stale: false },
    ]]);
    const color = createBuildingRentSampler(features, prices, { minimum: 12, maximum: 12 });
    expect(color(44.5, 40.2)).toBe("#facc15");
    expect(color(44.7, 40.2)).toBeNull();
  });

  it("calculates a building footprint location from vector tile geometry", () => {
    const center = footprintCenter({
      type: "Polygon",
      coordinates: [[[44.5, 40.1], [44.6, 40.1], [44.6, 40.2], [44.5, 40.2]]],
    });
    expect(center?.[0]).toBeCloseTo(44.55);
    expect(center?.[1]).toBeCloseTo(40.15);
  });
});
