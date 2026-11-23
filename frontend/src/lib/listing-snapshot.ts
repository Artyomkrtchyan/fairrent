import type { components } from "@/api/schema";

export type SnapshotListing = components["schemas"]["Listing"];
export type SnapshotMeasure = "month" | "m2";

export interface DistrictSnapshot {
  districtId: string;
  label: string;
  listingCount: number;
  pricedCount: number;
  areaPricedCount: number;
  medianMonthlyUsd: number | null;
  medianPerSqmUsd: number | null;
}

const DISTRICT_LABELS: Record<string, string> = {
  ajapnyak: "Ajapnyak",
  arabkir: "Arabkir",
  avan: "Avan",
  davtashen: "Davtashen",
  erebuni: "Erebuni",
  "kanaker-zeytun": "Kanaker-Zeytun",
  kentron: "Kentron",
  "malatia-sebastia": "Malatia-Sebastia",
  "nor-nork": "Nor Nork",
  "nork-marash": "Nork-Marash",
  nubarashen: "Nubarashen",
  shengavit: "Shengavit",
};

function validRent(value: number | null): value is number {
  return value !== null && Number.isFinite(value) && value > 0;
}

export function median(values: readonly number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  if (sorted.length % 2 !== 0) return sorted[middle]!;
  return (sorted[middle - 1]! + sorted[middle]!) / 2;
}

/** Only one row per property (where a stable deduplication ID is available). */
export function uniqueActiveListings(listings: readonly SnapshotListing[]): SnapshotListing[] {
  const seen = new Map<string, SnapshotListing>();
  for (const listing of listings) {
    if (listing.status !== "active") continue;
    const key = listing.dedup_group_id
      ? `dedup:${listing.dedup_group_id}`
      : listing.property_id
        ? `property:${listing.property_id}`
        : `listing:${listing.id}`;
    const earlier = seen.get(key);
    if (!earlier || listing.last_seen_at > earlier.last_seen_at) seen.set(key, listing);
  }
  return [...seen.values()];
}

export function buildDistrictSnapshot(listings: readonly SnapshotListing[]): DistrictSnapshot[] {
  const groups = new Map<string, SnapshotListing[]>();
  for (const listing of uniqueActiveListings(listings)) {
    if (!listing.district_id) continue;
    const group = groups.get(listing.district_id) ?? [];
    group.push(listing);
    groups.set(listing.district_id, group);
  }

  return [...groups].map(([districtId, group]) => {
    const monthly = group.map((item) => item.price_monthly_normalized).filter(validRent);
    const perSqm = group.flatMap((item) => {
      const rent = item.price_monthly_normalized;
      const area = item.area_sqm;
      return validRent(rent) && area !== null && Number.isFinite(area) && area > 0
        ? [rent / area] : [];
    });
    return {
      districtId,
      label: DISTRICT_LABELS[districtId] ?? districtId,
      listingCount: group.length,
      pricedCount: monthly.length,
      areaPricedCount: perSqm.length,
      medianMonthlyUsd: median(monthly),
      medianPerSqmUsd: median(perSqm),
    };
  }).sort((a, b) => a.label.localeCompare(b.label));
}

export function snapshotMedian(listings: readonly SnapshotListing[], measure: SnapshotMeasure): number | null {
  const unique = uniqueActiveListings(listings);
  if (measure === "month") {
    return median(unique.map((item) => item.price_monthly_normalized).filter(validRent));
  }
  return median(unique.flatMap((item) => {
    const rent = item.price_monthly_normalized;
    const area = item.area_sqm;
    return validRent(rent) && area !== null && Number.isFinite(area) && area > 0
      ? [rent / area] : [];
  }));
}
