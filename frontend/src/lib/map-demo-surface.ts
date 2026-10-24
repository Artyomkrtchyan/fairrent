/** Illustrative design fixture. Not a model, market estimate or measured coverage. */
export const DEMO_SURFACE = {
  bounds: [44.44, 40.11, 44.6, 40.24] as const,
  minimum: 6,
  maximum: 24,
  stops: ["#16a34a", "#facc15", "#f97316", "#dc2626"],
};

export function demoRentValue(x: number, y: number): number | null {
  if (((x - 0.5) / 0.49) ** 2 + ((y - 0.5) / 0.49) ** 2 > 1) return null;
  const peak = (cx: number, cy: number, spread: number) =>
    Math.exp(-((x - cx) ** 2 + (y - cy) ** 2) / spread);
  return Math.min(24, Math.max(6, 6 + 16 * peak(0.59, 0.58, 0.052) + 7 * peak(0.36, 0.3, 0.022)));
}

let cachedImage: string | undefined;

/** Smooth, geographic raster fixture; values and spatial pattern are entirely invented. */
export function demoSurfaceImage(): string {
  if (cachedImage) return cachedImage;
  const size = 256;
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
      const value = demoRentValue(col / (size - 1), row / (size - 1));
      if (value === null) continue;
      const scale = ((value - 6) / 18) * 3;
      const start = Math.min(2, Math.floor(scale));
      const mix = scale - start;
      const pixel = (row * size + col) * 4;
      for (let channel = 0; channel < 3; channel++) {
        image.data[pixel + channel] = Math.round(
          colors[start]![channel]! * (1 - mix) + colors[start + 1]![channel]! * mix,
        );
      }
      image.data[pixel + 3] = 210;
    }
  }
  context.putImageData(image, 0, 0);
  cachedImage = canvas.toDataURL("image/png");
  return cachedImage;
}
