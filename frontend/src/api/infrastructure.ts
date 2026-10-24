import { useInfiniteQuery } from "@tanstack/react-query";
import { api, apiMode } from "./client";
import type { components, paths } from "./schema";
import { parseMapBounds } from "@/lib/map-bounds";

export type InfrastructurePoint = components["schemas"]["InfrastructurePoint"];
export type InfrastructureQuery = paths["/api/v1/infrastructure"]["get"]["parameters"]["query"];

export async function getInfrastructure(query: InfrastructureQuery, signal?: AbortSignal) {
  const { data, error, response } = await api.GET("/api/v1/infrastructure", {
    params: { query },
    ...(signal ? { signal } : {}),
  });
  if (error || !data)
    throw new Error(error?.message ?? `Nearby places unavailable (${response.status}).`);
  return data;
}

export function useInfrastructure(bbox: string | undefined, metro: boolean, university: boolean) {
  const type = metro && university ? undefined : metro ? "metro" : "university";
  return useInfiniteQuery({
    queryKey: ["infrastructure", apiMode, bbox, type],
    enabled: !!parseMapBounds(bbox) && (metro || university),
    initialPageParam: 1,
    queryFn: ({ signal, pageParam }) => {
      if (!bbox) throw new Error("A bounded area is required.");
      return getInfrastructure(
        { bbox, page: pageParam, page_size: 100, ...(type ? { type } : {}) },
        signal,
      );
    },
    getNextPageParam: (last) => (last.has_more ? last.page + 1 : undefined),
    retry: false,
  });
}

export function hasInfrastructureCoordinates(point: InfrastructurePoint): boolean {
  return (
    Number.isFinite(point.latitude) &&
    Number.isFinite(point.longitude) &&
    point.latitude >= -90 &&
    point.latitude <= 90 &&
    point.longitude >= -180 &&
    point.longitude <= 180
  );
}
