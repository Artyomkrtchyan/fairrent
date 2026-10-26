import type { MarketIndex } from "@/api/market";

export type MarketMeasure = "month" | "m2";

export interface MarketChartPoint {
  timestamp: number;
  week: string;
  value: number | null;
  record: MarketIndex | null;
}

export function marketValue(record: MarketIndex, measure: MarketMeasure): number | null {
  const value = measure === "month" ? record.median_usd_month : record.median_usd_m2;

  return value !== null && Number.isFinite(value) ? value : null;
}

export function marketCount(record: MarketIndex, measure: MarketMeasure): number {
  return measure === "month" ? record.sample_count : record.area_sample_count;
}

export function buildMarketSeries(
  records: readonly MarketIndex[],
  measure: MarketMeasure,
): MarketChartPoint[] {
  const sorted = [...records].sort((a, b) => a.period_start.localeCompare(b.period_start));

  const result: MarketChartPoint[] = [];
  const weekLength = 7 * 24 * 60 * 60 * 1000;

  for (const record of sorted) {
    const timestamp = Date.parse(`${record.period_start}T00:00:00Z`);
    const previous = result.at(-1);

    if (previous && timestamp - previous.timestamp > weekLength) {
      const missingWeek = previous.timestamp + weekLength;

      result.push({
        timestamp: missingWeek,
        week: new Date(missingWeek).toISOString().slice(0, 10),
        value: null,
        record: null,
      });
    }

    result.push({
      timestamp,
      week: record.period_start,
      value: marketValue(record, measure),
      record,
    });
  }

  return result;
}
