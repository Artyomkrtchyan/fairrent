import type { MultiPolygon, Polygon } from "geojson";
import type { ExpressionSpecification } from "maplibre-gl";

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

/** Reject distant districts before evaluating their polygon edges. */
export function buildingRentPaint(
  districts: readonly { geometry: BuildingGeometry; properties: { rentColor: string } }[],
  fallback: string,
): ExpressionSpecification {
  const cases = districts.flatMap(({ geometry, properties }) => {
    const center = footprintCenter(geometry);
    if (!center) return [];
    let radius = 0;
    for (const polygon of polygonsOf(geometry)) {
      for (const [longitude, latitude] of polygon[0] ?? []) {
        radius = Math.max(radius, Math.hypot(longitude! - center[0], latitude! - center[1]));
      }
    }
    return [
      [
        "all",
        ["<=", ["distance", { type: "Point", coordinates: center }], radius * 112_000 + 100],
        ["==", ["distance", geometry], 0],
      ],
      properties.rentColor,
    ];
  });
  return ["case", ...cases, fallback] as ExpressionSpecification;
}
