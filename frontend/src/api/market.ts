import { api } from "./client";
import type { components, paths } from "./schema";

export type MarketIndex = components["schemas"]["MarketIndex"];
export type MarketIndexPage = components["schemas"]["MarketIndexPage"];

export type MarketQuery = NonNullable<paths["/api/v1/market-index"]["get"]["parameters"]["query"]>;

export class MarketApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "MarketApiError";
  }
}

export async function getMarketIndex(
  query: MarketQuery = {},
  signal?: AbortSignal,
): Promise<MarketIndexPage> {
  const { data, error, response } = await api.GET("/api/v1/market-index", {
    params: { query },
    ...(signal ? { signal } : {}),
  });

  if (error || !data) {
    throw new MarketApiError(error?.message ?? "Could not load market analytics.", response.status);
  }

  return data;
}
