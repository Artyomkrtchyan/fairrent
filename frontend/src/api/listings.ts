import { api } from "./client";
import type { components, paths } from "./schema";

export type ListingQuery = NonNullable<paths["/api/v1/listings"]["get"]["parameters"]["query"]>;
export type ListingMapQuery = NonNullable<
  paths["/api/v1/listings/map"]["get"]["parameters"]["query"]
>;
export type ListingMapPoint = components["schemas"]["ListingMapPoint"];

export class ListingApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ListingApiError";
  }
}

export async function getListings(signal?: AbortSignal, query: ListingQuery = {}) {
  const { data, error, response } = await api.GET("/api/v1/listings", {
    params: {
      query,
    },
    ...(signal ? { signal } : {}),
  });

  if (error || !data) {
    throw new ListingApiError(error?.message ?? "Could not load listings.", response.status);
  }

  return data;
}

export async function getListingDetails(id: string, signal?: AbortSignal) {
  const { data, error, response } = await api.GET("/api/v1/listings/{id}", {
    params: {
      path: { id },
    },
    ...(signal ? { signal } : {}),
  });

  if (error || !data) {
    throw new ListingApiError(error?.message ?? "Could not load listing details.", response.status);
  }

  return data;
}

export async function getListingMap(query: ListingMapQuery, signal: AbortSignal) {
  const { data, error, response } = await api.GET("/api/v1/listings/map", {
    params: { query },
    signal,
  });
  if (!data) {
    throw new ListingApiError(
      error?.message ?? "Could not load rental locations.",
      response.status,
    );
  }
  return data;
}

export async function getListingEstimate(id: string, signal: AbortSignal) {
  const { data, error, response } = await api.GET("/api/v1/listings/{id}/estimate", {
    params: { path: { id } },
    signal,
  });
  if (response.status === 404) return null;
  if (!data) {
    throw new ListingApiError(error?.message ?? "Could not load the estimate.", response.status);
  }
  return data;
}
