import type { components } from "@/api/schema";
import type { DistrictPrice } from "@/lib/district-price-layer";
import { buildDistrictSnapshot } from "@/lib/listing-snapshot";

type Listing = components["schemas"]["Listing"];

export interface SnapshotMapPrices {
  districtPrices: DistrictPrice[];
  min: number | null;
  max: number | null;
  latestObservation: string | null;
}

/**
 * Fallback for an unpopulated weekly index: derive district medians from
 * observed active listing rents / m². Never invent missing prices or areas.
 * Five distinct usable listings are required per colored district.
 */
export function snapshotMapPrices(listings: readonly Listing[]): SnapshotMapPrices {
  const summaries = buildDistrictSnapshot(listings);
  const districts = summaries
    .filter((district) =>
      district.areaPricedCount >= 5 &&
      district.medianPerSqmUsd !== null &&
      Number.isFinite(district.medianPerSqmUsd) &&
      district.medianPerSqmUsd > 0,
    )
    .map((district) => ({
      districtId: district.districtId,
      medianUsdM2: district.medianPerSqmUsd!,
      areaSampleCount: district.areaPricedCount,
      periodStart: "",
      periodEnd: "",
      stale: false,
    }));
  const validTimes = listings.map((item) => item.last_seen_at).filter(Boolean).sort();
  const values = districts.map((item) => item.medianUsdM2);
  return {
    districtPrices: districts,
    min: values.length ? Math.min(...values) : null,
    max: values.length ? Math.max(...values) : null,
    latestObservation: validTimes.at(-1) ?? null,
  };
}
