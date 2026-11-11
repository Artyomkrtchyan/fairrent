import type { DistrictPrice } from "@/lib/district-price-layer";

export type BuildingPolygon = number[][][];
export type BuildingGeometry = { type: "Polygon" | "MultiPolygon"; coordinates: unknown };
export type DistrictGeometry = {
  geometry: BuildingGeometry;
  properties: { district_id: string };
};

const GREEN = [34, 197, 94] as const;
const YELLOW = [250, 204, 21] as const;
const RED = [239, 68, 68] as const;

export function rentGradientColor(value: number): string {
  const normalized = Math.max(0, Math.min(1, value));
  const start = normalized < 0.5 ? GREEN : YELLOW;
  const end = normalized < 0.5 ? YELLOW : RED;
  const t = normalized < 0.5 ? normalized * 2 : (normalized - 0.5) * 2;
  return "#" + start.map((channel, index) =>
    Math.round(channel + (end[index]! - channel) * t).toString(16).padStart(2, "0"),
  ).join("");
}

function polygonsOf(geometry: BuildingGeometry): BuildingPolygon[] {
  return geometry.type === "Polygon"
    ? [geometry.coordinates as BuildingPolygon]
    : geometry.coordinates as BuildingPolygon[];
}

/** Center point of a (possibly tile-clipped) footprint, in geographic coordinates. */
export function footprintCenter(geometry: BuildingGeometry): [number, number] | null {
  const polygon = polygonsOf(geometry)[0];
  const ring = polygon?.[0];
  if (!ring?.length) return null;
  let longitude = 0;
  let latitude = 0;
  let count = 0;
  for (const point of ring) {
    if (!Number.isFinite(point[0]) || !Number.isFinite(point[1])) continue;
    longitude += point[0]!;
    latitude += point[1]!;
    count++;
  }
  return count ? [longitude / count, latitude / count] : null;
}

function insideRing(lng: number, lat: number, ring: number[][]): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const a = ring[i]!;
    const b = ring[j]!;
    if ((a[1]! > lat) !== (b[1]! > lat) &&
        lng < (b[0]! - a[0]!) * (lat - a[1]!) / (b[1]! - a[1]!) + a[0]!) {
      inside = !inside;
    }
  }
  return inside;
}

/**
 * Give a rental location and its matching building exactly the same color.
 * Supported district medians are authoritative; the former inverse-distance
 * surface could turn a high-rent district green near its boundary, then red
 * when different building geometry appeared at a closer zoom.
 *
 * We use the same continuous green-yellow-red *palette*, but sample each
 * district's observed median consistently instead of inventing block prices.
 */
export function createBuildingRentSampler(
  features: readonly DistrictGeometry[],
  prices: ReadonlyMap<string, DistrictPrice>,
  range: { minimum: number; maximum: number },
): (longitude: number, latitude: number) => string | null {
  const span = range.maximum - range.minimum;
  const city = features.flatMap((feature) => {
    const price = prices.get(feature.properties.district_id);
    if (!price || !Number.isFinite(price.medianUsdM2)) return [];
    const normalized = span > 0
      ? (price.medianUsdM2 - range.minimum) / span
      : 0.5;
    const rentColor = rentGradientColor(normalized);
    return polygonsOf(feature.geometry).map((polygon) => {
      let west = Infinity, east = -Infinity, south = Infinity, north = -Infinity;
      for (const point of polygon[0] ?? []) {
        west = Math.min(west, point[0]!);
        east = Math.max(east, point[0]!);
        south = Math.min(south, point[1]!);
        north = Math.max(north, point[1]!);
      }
      return { polygon, west, east, south, north, rentColor };
    });
  });

  return (longitude, latitude) => {
    if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) return null;
    for (const district of city) {
      if (longitude < district.west || longitude > district.east ||
          latitude < district.south || latitude > district.north) continue;
      const exterior = district.polygon[0];
      if (exterior && insideRing(longitude, latitude, exterior) &&
          !district.polygon.slice(1).some((hole) => insideRing(longitude, latitude, hole))) {
        return district.rentColor;
      }
    }
    return null;
  };
}
