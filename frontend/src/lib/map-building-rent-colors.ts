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

/** Sample the exact spatial interpolation and green-yellow-red palette used by the ground surface. */
export function createBuildingRentSampler(
  features: readonly DistrictGeometry[],
  prices: ReadonlyMap<string, DistrictPrice>,
  range: { minimum: number; maximum: number },
): (longitude: number, latitude: number) => string | null {
  // Precompute bounding boxes so a city-wide set of vector footprints does not
  // repeatedly scan every coordinate of every district on each map movement.
  const city = features.flatMap((feature) => polygonsOf(feature.geometry)).map((polygon) => {
    let west = Infinity, east = -Infinity, south = Infinity, north = -Infinity;
    for (const point of polygon[0] ?? []) {
      west = Math.min(west, point[0]!);
      east = Math.max(east, point[0]!);
      south = Math.min(south, point[1]!);
      north = Math.max(north, point[1]!);
    }
    return { polygon, west, east, south, north };
  });
  const anchors: { lng: number; lat: number; normalized: number }[] = [];
  for (const feature of features) {
    const price = prices.get(feature.properties.district_id);
    if (!price) continue;
    // Select the largest district outer ring, as with the raster surface.
    let selected: { center: [number, number]; area: number } | undefined;
    for (const polygon of polygonsOf(feature.geometry)) {
      const ring = polygon[0];
      if (!ring?.length) continue;
      let area = 0;
      let cx = 0;
      let cy = 0;
      for (let i = 0; i < ring.length; i++) {
        const a = ring[i]!, b = ring[(i + 1) % ring.length]!;
        const cross = a[0]! * b[1]! - b[0]! * a[1]!;
        area += cross;
        cx += (a[0]! + b[0]!) * cross;
        cy += (a[1]! + b[1]!) * cross;
      }
      if (Math.abs(area) > 1e-12 && (!selected || Math.abs(area) > selected.area)) {
        selected = { center: [cx / (3 * area), cy / (3 * area)], area: Math.abs(area) };
      }
    }
    if (!selected) continue;
    const span = range.maximum - range.minimum;
    anchors.push({
      lng: selected.center[0],
      lat: selected.center[1],
      normalized: span > 0 ? Math.max(0, Math.min(1, (price.medianUsdM2 - range.minimum) / span)) : 0.5,
    });
  }
  if (!anchors.length) return () => null;
  const meanLat = anchors.reduce((total, item) => total + item.lat, 0) / anchors.length;
  const lonScale = Math.cos(meanLat * Math.PI / 180);

  return (longitude, latitude) => {
    // Never color buildings outside the provided city district geometry.
    if (!city.some(({ polygon, west, east, south, north }) => {
      if (longitude < west || longitude > east || latitude < south || latitude > north) return false;
      const exterior = polygon[0];
      return exterior && insideRing(longitude, latitude, exterior) &&
        !polygon.slice(1).some((hole) => insideRing(longitude, latitude, hole));
    })) return null;

    let sum = 0;
    let weighted = 0;
    for (const anchor of anchors) {
      const dx = (longitude - anchor.lng) * lonScale;
      const dy = latitude - anchor.lat;
      const weight = 1 / (dx * dx + dy * dy + 0.000025);
      sum += weight;
      weighted += weight * anchor.normalized;
    }
    return rentGradientColor(0.5 + (weighted / sum - 0.5) * 1.35);
  };
}

/** Select a stable icon color from the same continuous gradient as the footprints. */
export function nearestBuildingRentColorIndex(hex: string, steps = 21): number {
  if (!/^#[0-9a-fA-F]{6}$/.test(hex)) return Math.floor((steps - 1) / 2);
  const rgb = [1, 3, 5].map((offset) => parseInt(hex.slice(offset, offset + 2), 16));
  let bestIndex = 0;
  let bestDistance = Infinity;
  for (let index = 0; index < steps; index++) {
    const sample = rentGradientColor(index / (steps - 1));
    const candidate = [1, 3, 5].map((offset) => parseInt(sample.slice(offset, offset + 2), 16));
    const distance = candidate.reduce((sum, channel, idx) =>
      sum + (channel - rgb[idx]!) ** 2, 0);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestIndex = index;
    }
  }
  return bestIndex;
}
