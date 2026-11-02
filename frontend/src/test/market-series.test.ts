import { describe, expect, it } from "vitest";
import fixtures from "../../../contracts/fixtures.json";
import type { MarketIndex } from "@/api/market";
import { mockMarketPage } from "@/api/mock-market";
import { buildMarketSeries, marketCount, marketValue } from "@/lib/market-series";

const base = fixtures["market-index"].value.items[0] as MarketIndex;

function marketUrl(query: string) {
  return new URL(`https://mock.fairrent.invalid/api/v1/market-index?${query}`);
}

describe("market chart values", () => {
  it("uses the API values for each measure", () => {
    expect(marketValue(base, "month")).toBe(600);
    expect(marketValue(base, "m2")).toBe(12);
  });

  it("keeps the two sample counts independent", () => {
    const record = {
      ...base,
      sample_count: 8,
      area_sample_count: 2,
      median_usd_m2: null,
    };

    expect(marketCount(record, "month")).toBe(8);
    expect(marketCount(record, "m2")).toBe(2);
    expect(marketValue(record, "month")).toBe(600);
    expect(marketValue(record, "m2")).toBeNull();
  });

  it("inserts a gap for an unpublished week without changing the input", () => {
    const later = {
      ...base,
      period_start: "2026-10-26",
      period_end: "2026-11-01",
      median_usd_month: 700,
    };
    const records = [later, base];
    const series = buildMarketSeries(records, "month");

    expect(series.map((point) => point.week)).toEqual(["2026-10-12", "2026-10-19", "2026-10-26"]);
    expect(series.map((point) => point.value)).toEqual([600, null, 700]);
    expect(series[1]?.record).toBeNull();
    expect(records[0]).toBe(later);
  });

  it("preserves unavailable values instead of converting them to zero", () => {
    const record = {
      ...base,
      median_usd_month: null,
      median_usd_m2: null,
    };

    expect(buildMarketSeries([record], "month")[0]?.value).toBeNull();
    expect(buildMarketSeries([], "month")).toEqual([]);
    expect(marketValue({ ...base, median_usd_month: 0 }, "month")).toBe(0);
  });
});

describe("mock market filters", () => {
  it("filters neighborhoods without inventing results", () => {
    const result = mockMarketPage(marketUrl("district_id=arabkir"));

    expect(result?.items).toEqual([]);
    expect(result?.total).toBe(0);
    expect(result?.available_from).toBeNull();
  });

  it("uses inclusive week-start filters and preserves available coverage", () => {
    const match = mockMarketPage(
      marketUrl("district_id=kentron&period_start=2026-10-12&period_end=2026-10-12"),
    );
    expect(match?.items).toHaveLength(1);

    const empty = mockMarketPage(marketUrl("district_id=kentron&period_start=2026-10-13"));
    expect(empty?.items).toEqual([]);
    expect(empty?.available_from).toBe("2026-10-12");
    expect(empty?.available_to).toBe("2026-10-12");
  });

  it("preserves the total on an empty later page", () => {
    const result = mockMarketPage(marketUrl("page=2&page_size=1"));

    expect(result?.items).toEqual([]);
    expect(result?.total).toBe(1);
    expect(result?.has_more).toBe(false);
  });

  it.each([
    "period_start=2026-02-30",
    "period_start=2026-10-20&period_end=2026-10-01",
    "page=0",
    "page_size=101",
    "page=1&page=2",
    "unknown=value",
  ])("rejects invalid filters: %s", (query) => {
    expect(mockMarketPage(marketUrl(query))).toBeUndefined();
  });
});
