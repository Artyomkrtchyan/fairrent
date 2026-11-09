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

  // Generate one fixed-size, data-driven image rather than recomputing on
  // camera changes. All districts contribute to one uninterrupted surface.
  const size = 512;
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
      let totalWeight = 0;
      let weightedPrice = 0;
      for (const anchor of anchors) {
        const dx = (longitude - anchor.longitude) * xScale;
        const dy = latitude - anchor.latitude;
        // Smooth inverse-distance weighting. Do not invent street-level values:
        // the raster is a visual blend of district-level medians only.
        const weight = 1 / (dx * dx + dy * dy + 0.000025);
        totalWeight += weight;
        weightedPrice += weight * anchor.normalized;
      }
      const normalized = weightedPrice / totalWeight;
      const value = Math.max(0, Math.min(1, 0.5 + (normalized - 0.5) * 1.35));
      const t = value < 0.5 ? value * 2 : (value - 0.5) * 2;
      const start = value < 0.5 ? [34, 197, 94] : [250, 204, 21];
      const finish = value < 0.5 ? [250, 204, 21] : [239, 68, 68];
      const offset = (y * size + x) * 4;
      for (let channel = 0; channel < 3; channel++) {
        pixels.data[offset + channel] = Math.round(start[channel]! * (1 - t) + finish[channel]! * t);
      }
      pixels.data[offset + 3] = 255;
    }
  }
  context.putImageData(pixels, 0, 0);

  // Mask to the *actual Yerevan district geometries*, not a rectangular,
  // elliptical, or distance-limited fade. Each polygon uses even/odd filling
  // so that inner rings remain holes. Shared district edges are not outlined.
  const mask = document.createElement("canvas");
  mask.width = size;
  mask.height = size;
  const maskContext = mask.getContext("2d");
  if (!maskContext) throw new Error("Cannot create the city boundary mask.");
  maskContext.fillStyle = "#fff";
  for (const feature of features) {
    const polygons: Polygon[] = feature.geometry.type === "Polygon"
      ? [feature.geometry.coordinates as Polygon]
      : feature.geometry.coordinates as Polygon[];
    for (const polygon of polygons) {
      maskContext.beginPath();
      for (const ring of polygon) {
        ring.forEach((point, index) => {
          const x = ((point[0]! - west) / longitudeSpan) * size;
          const y = ((north - point[1]!) / latitudeSpan) * size;
          if (index === 0) maskContext.moveTo(x, y);
          else maskContext.lineTo(x, y);
        });
        maskContext.closePath();
      }
      maskContext.fill("evenodd");
    }
  }
  context.globalCompositeOperation = "destination-in";
  context.drawImage(mask, 0, 0);
  context.globalCompositeOperation = "source-over";
  return { bounds: [west, south, east, north], url: canvas.toDataURL("image/png") };
}
