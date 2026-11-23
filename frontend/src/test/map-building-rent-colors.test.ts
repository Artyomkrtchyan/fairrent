import { describe, expect, it, vi } from "vitest";
import { createBuildingColorCache, footprintCenter, rentGradientColor } from "@/lib/map-building-rent-colors";

describe("native building rent colors", () => {
  it("uses the green-yellow-red palette", () => {
    expect(rentGradientColor(0)).toBe("#22c55e");
    expect(rentGradientColor(0.5)).toBe("#facc15");
    expect(rentGradientColor(1)).toBe("#ef4444");
  });

  it("keeps one color per feature ID across tile fragments", () => {
    const polygon = (west: number, east: number) => ({
      type: "Polygon" as const,
      coordinates: [[[west, 40.16], [east, 40.16], [east, 40.20], [west, 40.20], [west, 40.16]]],
    });
    const color = createBuildingColorCache([
      { geometry: polygon(44.48, 44.54), properties: { rentColor: "#ef4444" } },
      { geometry: polygon(44.54, 44.60), properties: { rentColor: "#facc15" } },
    ]);
    const firstFragment = () => polygon(44.52, 44.54);
    const nextFragment = vi.fn(() => polygon(44.54, 44.56));

    expect(color(123, firstFragment)).toBe("#ef4444");
    expect(color("123", nextFragment)).toBeUndefined();
    expect(nextFragment).not.toHaveBeenCalled();
    expect(color(124, nextFragment)).toBe("#facc15");
    expect(color(125, () => polygon(44.62, 44.65))).toBeUndefined();
  });

  it("calculates a representative point for a demo district", () => {
    const center = footprintCenter({
      type: "Polygon",
      coordinates: [[[44.5, 40.1], [44.6, 40.1], [44.6, 40.2], [44.5, 40.2]]],
    });
    expect(center?.[0]).toBeCloseTo(44.55);
    expect(center?.[1]).toBeCloseTo(40.15);
  });
});
