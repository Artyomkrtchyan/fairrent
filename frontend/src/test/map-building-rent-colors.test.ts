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

  it("keeps low- and high-zoom rental colors identical in expensive districts", () => {
    const features = [
      { properties: { district_id: "kentron" }, geometry: {
        type: "Polygon" as const,
        coordinates: [[[44.48, 40.16], [44.54, 40.16], [44.54, 40.20], [44.48, 40.20], [44.48, 40.16]]],
      }},
      { properties: { district_id: "other" }, geometry: {
        type: "Polygon" as const,
        coordinates: [[[44.55, 40.16], [44.60, 40.16], [44.60, 40.20], [44.55, 40.20], [44.55, 40.16]]],
      }},
    ];
    const prices = new Map<string, DistrictPrice>([
      ["kentron", { districtId: "kentron", medianUsdM2: 19.25, areaSampleCount: 608, periodStart: "2026-11-01", periodEnd: "2026-11-07", stale: false }],
      ["other", { districtId: "other", medianUsdM2: 10, areaSampleCount: 40, periodStart: "2026-11-01", periodEnd: "2026-11-07", stale: false }],
    ]);
    const sample = createBuildingRentSampler(features, prices, { minimum: 10, maximum: 19.25 });
    // House indicators and polygon fills use the same sampler regardless of zoom.
    expect(sample(44.51, 40.18)).toBe("#ef4444");
    expect(sample(44.53, 40.19)).toBe("#ef4444");
    expect(sample(44.57, 40.18)).toBe("#22c55e");
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
