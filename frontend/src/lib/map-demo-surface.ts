import districtGeojson from "@/data/yerevan-districts.geojson?raw";

/** Illustrative design fixture. NOT measured rent or a market estimate. */
type Ring = number[][];
type Polygon = Ring[];
const registry = JSON.parse(districtGeojson) as {
  features: Array<{
    geometry: { type: "Polygon" | "MultiPolygon"; coordinates: unknown };
  }>;
};
const polygons: Polygon[] = registry.features.flatMap((feature) =>
  feature.geometry.type === "Polygon"
    ? [feature.geometry.coordinates as Polygon]
    : feature.geometry.coordinates as Polygon[],
);
let west = Infinity, east = -Infinity, south = Infinity, north = -Infinity;
for (const polygon of polygons) {
  for (const ring of polygon) {
    for (const point of ring) {
      west = Math.min(west, point[0]!);
      east = Math.max(east, point[0]!);
      south = Math.min(south, point[1]!);
      north = Math.max(north, point[1]!);
    }
  }
}

export const DEMO_SURFACE = {
  bounds: [west, south, east, north] as const,
  minimum: 6,
  maximum: 24,
  stops: ["#22c55e", "#facc15", "#ef4444"],
};

function insideRing(longitude: number, latitude: number, ring: Ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const a = ring[i]!, b = ring[j]!;
    const ay = a[1]!, by = b[1]!;
    if ((ay > latitude) !== (by > latitude) &&
      longitude < (b[0]! - a[0]!) * (latitude - ay) / (by - ay) + a[0]!) {
      inside = !inside;
    }
  }
  return inside;
}

function insideYerevan(longitude: number, latitude: number) {
  return polygons.some((polygon) =>
    polygon.length > 0 && insideRing(longitude, latitude, polygon[0]!) &&
    !polygon.slice(1).some((hole) => insideRing(longitude, latitude, hole)),
  );
}

function illustrativeRentValue(x: number, y: number) {
  const peak = (cx: number, cy: number, spread: number) =>
    Math.exp(-((x - cx) ** 2 + (y - cy) ** 2) / spread);
  return Math.min(24, Math.max(6, 6 + 16 * peak(0.59, 0.58, 0.052) + 7 * peak(0.36, 0.3, 0.022)));
}

export function demoRentValue(x: number, y: number): number | null {
  if (x < 0 || x > 1 || y < 0 || y > 1) return null;
  const longitude = west + x * (east - west);
  const latitude = north - y * (north - south);
  return insideYerevan(longitude, latitude) ? illustrativeRentValue(x, y) : null;
}

let cachedImage: string | undefined;

/** Draw an explicitly synthetic color field clipped to Yerevan's geometry. */
export function demoSurfaceImage(): string {
  if (cachedImage) return cachedImage;
  const size = 512;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("Could not prepare demo price layer");
  const image = context.createImageData(size, size);
  const colors = DEMO_SURFACE.stops.map((hex) =>
    [1, 3, 5].map((index) => parseInt(hex.slice(index, index + 2), 16)),
  );
  for (let row = 0; row < size; row++) {
    for (let col = 0; col < size; col++) {
      const value = illustrativeRentValue(col / (size - 1), row / (size - 1));
      const scale = ((value - DEMO_SURFACE.minimum) / (DEMO_SURFACE.maximum - DEMO_SURFACE.minimum)) * 2;
      const start = Math.min(1, Math.floor(scale));
      const mix = scale - start;
      const pixel = (row * size + col) * 4;
      for (let channel = 0; channel < 3; channel++) {
        image.data[pixel + channel] = Math.round(
          colors[start]![channel]! * (1 - mix) + colors[start + 1]![channel]! * mix,
        );
      }
      image.data[pixel + 3] = 255;
    }
  }
  context.putImageData(image, 0, 0);

  // A single geographic city mask avoids round edges, triangular crop
  // artifacts and seams between districts while preserving interior holes.
  const mask = document.createElement("canvas");
  mask.width = mask.height = size;
  const maskContext = mask.getContext("2d");
  if (!maskContext) throw new Error("Could not prepare demo boundary mask");
  maskContext.fillStyle = "#fff";
  for (const polygon of polygons) {
    maskContext.beginPath();
    for (const ring of polygon) {
      ring.forEach((point, index) => {
        const x = ((point[0]! - west) / (east - west)) * size;
        const y = ((north - point[1]!) / (north - south)) * size;
        if (index === 0) maskContext.moveTo(x, y);
        else maskContext.lineTo(x, y);
      });
      maskContext.closePath();
    }
    maskContext.fill("evenodd");
  }
  context.globalCompositeOperation = "destination-in";
  context.drawImage(mask, 0, 0);
  context.globalCompositeOperation = "source-over";
  cachedImage = canvas.toDataURL("image/png");
  return cachedImage;
}
