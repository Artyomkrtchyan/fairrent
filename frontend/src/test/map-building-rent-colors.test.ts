import { createExpression, type ICanonicalTileID } from "@maplibre/maplibre-gl-style-spec";
import { describe, expect, it } from "vitest";
import { buildingRentPaint, footprintCenter, rentGradientColor } from "@/lib/map-building-rent-colors";

describe("native building rent colors", () => {
  it("uses the green-yellow-red palette", () => {
    expect(rentGradientColor(0)).toBe("#22c55e");
    expect(rentGradientColor(0.5)).toBe("#facc15");
    expect(rentGradientColor(1)).toBe("#ef4444");
  });

  it("evaluates polygon colors consistently at different tile zooms", () => {
    const district = {
      geometry: {
        type: "Polygon" as const,
        coordinates: [[[44.48, 40.16], [44.54, 40.16], [44.54, 40.20], [44.48, 40.20], [44.48, 40.16]]],
      },
      properties: { rentColor: "#ef4444" },
    };
    const parsed = createExpression(buildingRentPaint([district], "#e2e8f0"), "layers[0].paint.fill-extrusion-color");
    if (parsed.result === "error") throw new Error(JSON.stringify(parsed.value));

    const expression = parsed.value;

    function evaluate(z: number, longitude: number, latitude: number) {
      const scale = 2 ** z;
      const worldX = (lng: number) => (lng + 180) / 360 * scale;
      const worldY = (lat: number) =>
        (1 - Math.asinh(Math.tan(lat * Math.PI / 180)) / Math.PI) / 2 * scale;
      const x = Math.floor(worldX(longitude));
      const y = Math.floor(worldY(latitude));
      const point = (lng: number, lat: number) => ({
        x: Math.round((worldX(lng) - x) * 8192),
        y: Math.round((worldY(lat) - y) * 8192),
      });
      const a = point(longitude, latitude);
      const b = point(longitude + 0.0001, latitude + 0.0001);
      return expression.evaluate(
        { zoom: z },
        { type: 3, properties: {}, geometry: [[a, { x: b.x, y: a.y }, b, { x: a.x, y: b.y }, a]] },
        {},
        { x, y, z } as ICanonicalTileID,
      );
    }

    expect(evaluate(14, 44.51, 40.18)).toBe("#ef4444");
    expect(evaluate(16, 44.51, 40.18)).toBe("#ef4444");
    expect(evaluate(14, 44.56, 40.18)).toBe("#e2e8f0");
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
