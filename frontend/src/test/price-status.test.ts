import { describe, expect, it } from "vitest";
import { assessLocation, priceStatus } from "@/lib/data";

describe("price comparison status", () => {
  it("is within when asking is inside the interval", () => {
    expect(priceStatus({ askingUsd: 900, interval: [800, 1000] })).toBe("within");
  });
  it("is above (not fraud) when asking exceeds the interval", () => {
    expect(priceStatus({ askingUsd: 2000, interval: [800, 1000] })).toBe("above");
  });
  it("is below when asking is under the interval", () => {
    expect(priceStatus({ askingUsd: 500, interval: [800, 1000] })).toBe("below");
  });
  it("is unavailable without an interval", () => {
    expect(priceStatus({ askingUsd: 500, interval: null })).toBe("unavailable");
  });
});

describe("location assessment", () => {
  it("gives no property-specific figure from coordinates alone", () => {
    expect(assessLocation(40.1872, 44.5152).property).toBeNull();
  });
});
