import createClient from "openapi-fetch";
import type { paths } from "./schema";
import { mockFetch } from "./mock";

const configuredMode = import.meta.env["VITE_API_MODE"] ?? "mock";

if (configuredMode !== "mock" && configuredMode !== "real") {
  throw new Error("VITE_API_MODE must be 'mock' or 'real'.");
}

export const apiMode = configuredMode;

const configuredBaseUrl = import.meta.env["VITE_API_BASE_URL"]?.trim();
export const apiBaseUrl = configuredBaseUrl || window.location.origin;

export const api = createClient<paths>({
  baseUrl: apiMode === "mock" ? "https://mock.fairrent.invalid" : apiBaseUrl,

  fetch: apiMode === "mock" ? mockFetch : globalThis.fetch.bind(globalThis),
});
