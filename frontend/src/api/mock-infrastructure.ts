import fixtures from "../../../contracts/fixtures.json";
import type { InfrastructurePoint } from "./infrastructure";
import { parseMapBounds } from "@/lib/map-bounds";

/** Development-only examples; neither names nor locations describe real facilities. */
export const mockInfrastructure: readonly InfrastructurePoint[] = [
  ...(fixtures.infrastructure.value.items as InfrastructurePoint[]),
  {
    id: "synthetic-university-1",
    name: "Synthetic university",
    type: "university",
    latitude: 40.179,
    longitude: 44.526,
  },
];

export function mockInfrastructurePage(url: URL) {
  const bounds = parseMapBounds(url.searchParams.get("bbox"));
  const type = url.searchParams.get("type");
  const page = Number(url.searchParams.get("page") ?? 1);
  const size = Number(url.searchParams.get("page_size") ?? 20);
  if (
    !bounds ||
    (type !== null && type !== "metro" && type !== "university") ||
    !Number.isSafeInteger(page) ||
    page < 1 ||
    !Number.isSafeInteger(size) ||
    size < 1 ||
    size > 100
  )
    return undefined;
  const [west, south, east, north] = bounds;
  const points = mockInfrastructure
    .filter(
      (point) =>
        (!type || point.type === type) &&
        point.longitude >= west &&
        point.longitude <= east &&
        point.latitude >= south &&
        point.latitude <= north,
    )
    .sort((a, b) => a.id.localeCompare(b.id));
  return {
    items: points.slice((page - 1) * size, page * size),
    page,
    page_size: size,
    total: points.length,
    has_more: page * size < points.length,
  };
}
