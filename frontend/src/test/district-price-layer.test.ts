import { describe, expect, it } from "vitest";
import type { MarketIndex } from "@/api/market";
import { summarizeDistrictPrices } from "@/lib/district-price-layer";

function weekly(
  district_id: string,
  period_start: string,
  median_usd_m2: number | null,
  area_sample_count = 8,
  is_stale = false,
): MarketIndex {
  return {
    district_id,
    period_start,
    period_end: "2026-11-08",
    median_usd_m2,
    median_usd_month: 500,
    area_sample_count,
    sample_count: 8,
    status: "available",
    measure: "asking_price",
    data_as_of: "2026-11-08T00:00:00Z",
    freshness: {
      is_stale,
      data_as_of: "2026-11-08T00:00:00Z",
      generated_at: "2026-11-08T00:00:00Z",
      max_age_days: 14,
      policy_version: "test",
    },
  };
}

describe("district median rent layer", () => {
  it("uses a single latest supported weekly bucket, never mixing older district figures", () => {
    const result = summarizeDistrictPrices([
      weekly("kentron", "2026-10-26", 20),
      weekly("arabkir", "2026-11-02", 10),
      weekly("kentron", "2026-11-02", 16, 10, true),
    ]);
    expect(result.latest.map((item) => item.districtId)).toEqual(["arabkir", "kentron"]);
    expect(result.minimum).toBe(10);
    expect(result.maximum).toBe(16);
    expect(result.staleCount).toBe(1);
    expect(result.periodStart).toBe("2026-11-02");
    expect(result.latestPublishedPeriod).toBe("2026-11-02");
  });

  it("never colors null, invalid or undersampled per-square-meter records", () => {
    const result = summarizeDistrictPrices([
      weekly("kentron", "2026-11-02", null),
      weekly("arabkir", "2026-11-02", 12, 4),
      weekly("avan", "2026-11-02", 0),
      weekly("nork-marash", "2026-11-02", 15, 5),
    ]);
    expect(result.latest.map((item) => item.districtId)).toEqual(["nork-marash"]);
    expect(result.minimum).toBe(15);
    expect(result.maximum).toBe(15);
  });

  it("uses the most recent supported week when newer weekly data is sparse", () => {
    const result = summarizeDistrictPrices([
      weekly("kentron", "2026-10-26", 16, 10, true),
      weekly("arabkir", "2026-11-02", null, 10),
      weekly("kentron", "2026-11-02", 22, 3),
    ]);
    expect(result.periodStart).toBe("2026-10-26");
    expect(result.latestPublishedPeriod).toBe("2026-11-02");
    expect(result.latest.map((item) => item.districtId)).toEqual(["kentron"]);
    expect(result.staleCount).toBe(1);
  });

  it("does not present any colored district without a supported per-m² statistic", () => {
    const result = summarizeDistrictPrices([weekly("kentron", "2026-11-02", null)]);
    expect(result.periodStart).toBeNull();
    expect(result.latestPublishedPeriod).toBe("2026-11-02");
    expect(result.latest).toEqual([]);
  });

  it("shows no supported colors when the API publishes no data", () => {
    expect(summarizeDistrictPrices([])).toEqual({
      periodStart: null, periodEnd: null, latestPublishedPeriod: null, latest: [], minimum: null, maximum: null, staleCount: 0,
    });
  });
});
