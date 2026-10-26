export type MapBounds = [number, number, number, number];

/** C01: west,south,east,north; no crossing and at most 0.5° per axis. */
export function parseMapBounds(value: unknown): MapBounds | undefined {
  if (
    typeof value !== "string" ||
    !/^-?\d+(\.\d+)?,-?\d+(\.\d+)?,-?\d+(\.\d+)?,-?\d+(\.\d+)?$/.test(value)
  )
    return;
  const [west, south, east, north] = value.split(",").map(Number) as MapBounds;
  if (
    ![west, south, east, north].every(Number.isFinite) ||
    west < -180 ||
    east > 180 ||
    south < -90 ||
    north > 90 ||
    west >= east ||
    south >= north ||
    east - west > 0.5 ||
    north - south > 0.5
  )
    return;
  return [west, south, east, north];
}

export function serializeMapBounds(bounds: MapBounds): string {
  return bounds.map((value) => Number(value.toFixed(6))).join(",");
}
