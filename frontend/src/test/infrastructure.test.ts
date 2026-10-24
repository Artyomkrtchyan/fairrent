import { describe, expect, it } from "vitest";
import createClient from "openapi-fetch";
import { mockFetch } from "@/api/mock";
import type { paths } from "@/api/schema";
import { hasInfrastructureCoordinates } from "@/api/infrastructure";

const client = createClient<paths>({ baseUrl: "https://mock.fairrent.invalid", fetch: mockFetch });
const bbox = "44.5,40.17,44.55,40.20";

describe("bounded nearby-place transport", () => {
  it("filters type and returns only the selected facilities", async () => {
    const metro = await client.GET("/api/v1/infrastructure", {
      params: { query: { bbox, type: "metro" } },
    });
    const university = await client.GET("/api/v1/infrastructure", {
      params: { query: { bbox, type: "university" } },
    });
    expect(metro.data?.items.map((point) => point.type)).toEqual(["metro"]);
    expect(university.data?.items.map((point) => point.type)).toEqual(["university"]);
    expect(university.data?.items[0]?.name).toContain("Synthetic");
  });
  it("applies inclusive bbox limits and pages the result in stable id order", async () => {
    const first = await client.GET("/api/v1/infrastructure", {
      params: { query: { bbox, page_size: 1 } },
    });
    const second = await client.GET("/api/v1/infrastructure", {
      params: { query: { bbox, page_size: 1, page: 2 } },
    });
    expect(first.data?.total).toBe(2);
    expect(first.data?.has_more).toBe(true);
    expect(second.data?.has_more).toBe(false);
    expect(first.data?.items[0]?.id).not.toBe(second.data?.items[0]?.id);
    const boundary = await client.GET("/api/v1/infrastructure", {
      params: { query: { bbox: "44.515,40.185,44.52,40.19" } },
    });
    expect(boundary.data?.items.map((point) => point.id)).toEqual(["synthetic-metro-1"]);
  });
  it("reports empty areas without inserting fallback locations", async () => {
    const result = await client.GET("/api/v1/infrastructure", {
      params: { query: { bbox: "44.0,40.0,44.1,40.1" } },
    });
    expect(result.data?.items).toEqual([]);
    expect(result.data?.total).toBe(0);
  });
  it.each(["bad", "44,40,45,41", "45,40,44,40.1"])("rejects invalid bounds: %s", async (bbox) => {
    const result = await client.GET("/api/v1/infrastructure", { params: { query: { bbox } } });
    expect(result.response.status).toBe(422);
  });
  it("excludes invalid place coordinates from marker candidates", () => {
    const point = {
      id: "test",
      name: "Test",
      type: "metro" as const,
      latitude: 40.18,
      longitude: 44.51,
    };
    expect(hasInfrastructureCoordinates(point)).toBe(true);
    expect(hasInfrastructureCoordinates({ ...point, latitude: NaN })).toBe(false);
    expect(hasInfrastructureCoordinates({ ...point, longitude: 190 })).toBe(false);
  });
});
