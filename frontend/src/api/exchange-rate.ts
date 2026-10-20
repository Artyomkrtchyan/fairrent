import { useQuery } from "@tanstack/react-query";
import { api, apiMode } from "./client";

export function useExchangeRate() {
  const query = useQuery({
    queryKey: ["exchange-rate", apiMode],

    queryFn: async ({ signal }) => {
      const { data, error } = await api.GET("/api/v1/exchange-rate", { signal });

      if (error || !data) {
        throw new Error(error?.message ?? "Exchange rate unavailable.");
      }

      return data;
    },

    retry: false,

    // Periodically recheck the server's freshness assessment.
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
  });

  const rate = query.data;

  const canConvert =
    !query.isError &&
    !query.isFetching &&
    rate !== undefined &&
    rate.status !== "unavailable" &&
    rate.status !== "stale" &&
    !rate.freshness.is_stale &&
    rate.amd_per_usd !== null &&
    Number.isFinite(rate.amd_per_usd) &&
    rate.amd_per_usd > 0;

  return {
    ...query,
    rate,
    canConvert,
  };
}
