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
  latestPublishedPeriod: string | null;
  latest: DistrictPrice[];
  minimum: number | null;
  maximum: number | null;
  staleCount: number;
}

/**
 * Prefer the most recent published week that contains at least one supported
 * per-square-metre observation. Never combine figures from different weeks.
 * Do not invent values for missing districts or fall back to asking rent/month.
 * Preserve the latest publication week separately for a truthful age warning.
 */
export function summarizeDistrictPrices(records: readonly MarketIndex[]): PriceLayerSummary {
  const latestPublishedPeriod = records.reduce<string | null>(
    (latest, item) => (!latest || item.period_start > latest ? item.period_start : latest),
    null,
  );
  const supported = records.filter(
    (item) =>
      typeof item.median_usd_m2 === "number" &&
      Number.isFinite(item.median_usd_m2) &&
      item.median_usd_m2 > 0 &&
      item.area_sample_count >= 5,
  );
  const periodStart = supported.reduce<string | null>(
    (latest, item) => (!latest || item.period_start > latest ? item.period_start : latest),
    null,
  );
  if (!periodStart) {
    return {
      periodStart: null,
      periodEnd: null,
      latestPublishedPeriod,
      latest: [],
      minimum: null,
      maximum: null,
      staleCount: 0,
    };
  }
  const latest = supported
    .filter((item) => item.period_start === periodStart)
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
    periodEnd: latest[0]?.periodEnd ?? null,
    latestPublishedPeriod,
    latest,
    minimum: Math.min(...values),
    maximum: Math.max(...values),
    staleCount: latest.filter((item) => item.stale).length,
  };
}
