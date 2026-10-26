import { describe, expect, it } from "vitest";
import { DEMO_SURFACE, demoRentValue } from "@/lib/map-demo-surface";

describe("synthetic design surface", () => {
  it("has no invented measurements outside the explicit demo extent", () => {
    expect(demoRentValue(0, 0)).toBeNull();
    expect(demoRentValue(1, 1)).toBeNull();
  });
  it("provides a repeatable spatially varying fixture in the labelled scale", () => {
    const values: number[] = [];
    for (let y = 0; y <= 1; y += 0.05)
      for (let x = 0; x <= 1; x += 0.05) {
        const value = demoRentValue(x, y);
        if (value === null) continue;
        expect(value).toBeGreaterThanOrEqual(DEMO_SURFACE.minimum);
        expect(value).toBeLessThanOrEqual(DEMO_SURFACE.maximum);
        expect(demoRentValue(x, y)).toBe(value);
        values.push(value);
      }
    expect(Math.max(...values) - Math.min(...values)).toBeGreaterThan(12);
  });
});
