import type { DistrictPrice } from "@/lib/district-price-layer";

type Polygon = number[][][];
type Shape = { type: "Polygon" | "MultiPolygon"; coordinates: unknown };
type DistrictFeature = { geometry: Shape; properties: { district_id: string; name: string } };
type Anchor = { longitude: number; latitude: number; normalized: number };

// Interpolate *observed district medians* for presentation only. The resulting
// continuous colors are not street-level estimates and must not be used as prices.
export function renderSmoothRentSurface(
  features: readonly DistrictFeature[],
  prices: ReadonlyMap<string, DistrictPrice>,
  range: { minimum: number; maximum: number },
): { bounds: [number, number, number, number]; url: string } {
  const anchors: Anchor[] = [];
  let west = Infinity, south = Infinity, east = -Infinity, north = -Infinity;

  for (const feature of features) {
    const polygons: Polygon[] = feature.geometry.type === "Polygon"
      ? [feature.geometry.coordinates as Polygon]
      : feature.geometry.coordinates as Polygon[];
    let chosen: { longitude: number; latitude: number; area: number } | null = null;
    for (const polygon of polygons) {
      const ring = polygon[0];
      if (!ring?.length) continue;
      let doubleArea = 0, cx = 0, cy = 0;
      for (let i = 0; i < ring.length; i++) {
        const a = ring[i]!, b = ring[(i + 1) % ring.length]!;
        const cross = a[0]! * b[1]! - b[0]! * a[1]!;
        doubleArea += cross;
        cx += (a[0]! + b[0]!) * cross;
        cy += (a[1]! + b[1]!) * cross;
        west = Math.min(west, a[0]!);
        east = Math.max(east, a[0]!);
        south = Math.min(south, a[1]!);
        north = Math.max(north, a[1]!);
      }
      const area = Math.abs(doubleArea);
      if (area > 1e-12 && (!chosen || area > chosen.area)) {
        chosen = { longitude: cx / (3 * doubleArea), latitude: cy / (3 * doubleArea), area };
      }
    }
    const price = prices.get(feature.properties.district_id);
    if (chosen && price) {
      const span = range.maximum - range.minimum;
      anchors.push({
        longitude: chosen.longitude,
        latitude: chosen.latitude,
        normalized: span > 0 ? Math.max(0, Math.min(1, (price.medianUsdM2 - range.minimum) / span)) : 0.5,
      });
    }
  }
  if (!anchors.length || !Number.isFinite(west) || !Number.isFinite(north)) {
    throw new Error("Cannot render a rent gradient without supported district prices.");
  }

  // Render once per data update, not on pan/zoom. A bounded 320px raster keeps
  // the expanded map responsive and has no district polygon seams.
  const size = 320;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("Cannot create the rent gradient canvas.");
  const pixels = context.createImageData(size, size);
  const longitudeSpan = east - west;
  const latitudeSpan = north - south;
  const xScale = Math.cos(((south + north) / 2) * Math.PI / 180);

  for (let y = 0; y < size; y++) {
    const latitude = north - ((y + 0.5) / size) * latitudeSpan;
    for (let x = 0; x < size; x++) {
      const longitude = west + ((x + 0.5) / size) * longitudeSpan;
      let totalWeight = 0, weightedPrice = 0, nearestDistance = Infinity;
      for (const anchor of anchors) {
        const dx = (longitude - anchor.longitude) * xScale;
        const dy = latitude - anchor.latitude;
        const squaredDistance = dx * dx + dy * dy;
        nearestDistance = Math.min(nearestDistance, Math.sqrt(squaredDistance));
        const weight = 1 / (squaredDistance + 0.000075);
        totalWeight += weight;
        weightedPrice += weight * anchor.normalized;
      }
      const value = weightedPrice / totalWeight;
      // Green -> pure yellow -> red, with no additional orange band or hard edge.
      const t = value < 0.5 ? value * 2 : (value - 0.5) * 2;
      const start = value < 0.5 ? [22, 163, 74] : [250, 204, 21];
      const finish = value < 0.5 ? [250, 204, 21] : [220, 38, 38];
      const offset = (y * size + x) * 4;
      for (let channel = 0; channel < 3; channel++) {
        pixels.data[offset + channel] = Math.round(start[channel]! * (1 - t) + finish[channel]! * t);
      }
      // Fade into the map at the outer boundary and outside measured areas.
      const edge = Math.min(x, y, size - x - 1, size - y - 1) / 15;
      const maxDistance = Math.max(longitudeSpan * xScale, latitudeSpan) * 0.33;
      const coverage = Math.max(0, Math.min(1, (maxDistance - nearestDistance) / (maxDistance * 0.45)));
      pixels.data[offset + 3] = Math.round(245 * Math.min(1, edge) * coverage);
    }
  }
  context.putImageData(pixels, 0, 0);
  return { bounds: [west, south, east, north], url: canvas.toDataURL("image/png") };
}
