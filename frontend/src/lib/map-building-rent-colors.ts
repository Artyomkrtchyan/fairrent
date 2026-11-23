import type { Geometry, MultiPolygon, Polygon } from "geojson";

type BuildingPolygon = number[][][];
type BuildingGeometry = Polygon | MultiPolygon;

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
    ? [geometry.coordinates]
    : geometry.coordinates;
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

function insideRing(longitude: number, latitude: number, ring: number[][]): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [x, y] = ring[i]!;
    const [previousX, previousY] = ring[j]!;
    if ((y! > latitude) !== (previousY! > latitude) &&
        longitude < x! + (previousX! - x!) * (latitude - y!) / (previousY! - y!)) {
      inside = !inside;
    }
  }
  return inside;
}

export function createBuildingColorCache(
  districts: readonly { geometry: BuildingGeometry; properties: { rentColor: string } }[],
) {
  const polygons = districts.flatMap(({ geometry, properties }) =>
    polygonsOf(geometry).flatMap(([outer, ...holes]) => {
      if (!outer?.length) return [];
      const longitude = outer.map((point) => point[0]!);
      const latitude = outer.map((point) => point[1]!);
      return [{
        outer, holes, rentColor: properties.rentColor,
        west: Math.min(...longitude), east: Math.max(...longitude),
        south: Math.min(...latitude), north: Math.max(...latitude),
      }];
    }),
  );
  const assigned = new Set<string>();
  return (id: string | number, readGeometry: () => Geometry): string | undefined => {
    const key = String(id);
    if (assigned.has(key)) return undefined;
    assigned.add(key);
    const geometry = readGeometry();
    if (geometry.type !== "Polygon" && geometry.type !== "MultiPolygon") return undefined;
    const center = footprintCenter(geometry);
    if (!center) return undefined;
    const [longitude, latitude] = center;
    return polygons.find(({ west, east, south, north, outer, holes }) =>
      longitude >= west && longitude <= east && latitude >= south && latitude <= north &&
      insideRing(longitude, latitude, outer) &&
      !holes.some((hole) => insideRing(longitude, latitude, hole)),
    )?.rentColor;
  };
}
