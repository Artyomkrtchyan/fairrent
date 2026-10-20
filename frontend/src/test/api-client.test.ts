import { describe, expect, it } from "vitest";
import createClient from "openapi-fetch";
import fixtures from "../../../contracts/fixtures.json";
import type { paths } from "../api/schema";
import { mockFetch } from "../api/mock";

const client = createClient<paths>({
  baseUrl: "https://mock.fairrent.invalid",
  fetch: mockFetch,
});

describe("C01 mock API", () => {
  it("returns the shared listing response without its fixture wrapper", async () => {
    const { data, error } = await client.GET("/api/v1/listings");

    expect(error).toBeUndefined();
    expect(data).toEqual(fixtures.listings.value);
  });

  it("returns the matching listing details", async () => {
    const id = fixtures["listing-detail"].value.listing.id;

    const { data } = await client.GET("/api/v1/listings/{id}", {
      params: {
        path: { id },
      },
    });

    expect(data).toEqual(fixtures["listing-detail"].value);
  });

  it("requires authentication for reviews", async () => {
    const { response } = await client.GET("/api/v1/reviews");

    expect(response.status).toBe(401);
  });
});
