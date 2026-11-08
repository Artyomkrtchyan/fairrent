import type { MarketIndex } from "@/api/market";

export interface DistrictPrice {
  districtId: string;
  medianUsdM2: number;
  areaSampleCount: number;
  periodStart: string;
  periodEnd: string;
  stale: boolean;
}

export interface PriceLayerSummary {
  periodStart: string | null;
  periodEnd: string | null;
  latest: DistrictPrice[];
  minimum: number | null;
  maximum: number | null;
  staleCount: number;
}

/**
 * Choose one shared weekly observation period for a comparable, non-interpolated
 * district map. Never mix a previous district's week into the current one.
 * Null and undersampled USD/m² values stay uncolored.
 */
export function summarizeDistrictPrices(records: readonly MarketIndex[]): PriceLayerSummary {
  const periodStart = records.reduce<string | null>(
    (latest, item) => (!latest || item.period_start > latest ? item.period_start : latest),
    null,
  );
  if (!periodStart) {
    return { periodStart: null, periodEnd: null, latest: [], minimum: null, maximum: null, staleCount: 0 };
  }
  const sameWeek = records.filter((item) => item.period_start === periodStart);
  const latest = sameWeek
    .filter(
      (item) =>
        typeof item.median_usd_m2 === "number" &&
        Number.isFinite(item.median_usd_m2) &&
        item.median_usd_m2 > 0 &&
        item.area_sample_count >= 5,
    )
    .map((item) => ({
      districtId: item.district_id,
      medianUsdM2: item.median_usd_m2!,
      areaSampleCount: item.area_sample_count,
      periodStart: item.period_start,
      periodEnd: item.period_end,
      stale: item.freshness.is_stale,
    }));
  const values = latest.map((item) => item.medianUsdM2);
  return {
    periodStart,
    periodEnd: sameWeek[0]?.period_end ?? null,
    latest,
    minimum: values.length ? Math.min(...values) : null,
    maximum: values.length ? Math.max(...values) : null,
    staleCount: latest.filter((item) => item.stale).length,
  };
}
