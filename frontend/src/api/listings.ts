import { api } from "./client";

export class ListingApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ListingApiError";
  }
}

export async function getListings(signal?: AbortSignal) {
  const { data, error, response } = await api.GET("/api/v1/listings", {
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
