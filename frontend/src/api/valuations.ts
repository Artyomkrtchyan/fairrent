import { api } from "./client";
import type { components } from "./schema";

export async function requestValuation(body: components["schemas"]["ValuationRequest"]) {
  const { data, error } = await api.POST("/api/v1/valuations", { body });
  if (!data) {
    throw new Error(error?.message ?? "Could not assess this location.");
  }
  return data;
}
