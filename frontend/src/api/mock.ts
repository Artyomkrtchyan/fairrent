import fixtures from "../../../contracts/fixtures.json";
import { mockListingPage } from "./mock-listings";

type FixtureName = keyof typeof fixtures;

function fixtureResponse(name: FixtureName, status = 200): Response {
  return new Response(JSON.stringify(fixtures[name].value), {
    status,
    headers: {
      "Content-Type": "application/json",
    },
  });
}

/**
 * Development-only C01 fixture transport.
 * Does not simulate authentication, filtering or database writes.
 */
export const mockFetch: typeof fetch = async (input, init) => {
  const request = new Request(input, init);

  if (request.signal.aborted) {
    throw new DOMException("Request aborted", "AbortError");
  }

  const { pathname } = new URL(request.url);

  if (request.method !== "GET") {
    return fixtureResponse("error-service_unavailable", 503);
  }

  switch (pathname) {
    case "/api/v1/listings":
      return new Response(JSON.stringify(mockListingPage(new URL(request.url))), {
        status: 200,
        headers: {
          "Content-Type": "application/json",
        },
      });

    case "/api/v1/exchange-rate":
      return fixtureResponse("exchange-rate");

    case "/api/v1/market-index":
      return fixtureResponse("market-index");

    case "/api/v1/infrastructure":
      return fixtureResponse("infrastructure");

    case "/api/v1/reviews":
      return fixtureResponse("error-unauthenticated", 401);
  }

  const listingId = fixtures["listing-detail"].value.listing.id;

  if (pathname === `/api/v1/listings/${listingId}`) {
    return fixtureResponse("listing-detail");
  }

  if (pathname === `/api/v1/listings/${listingId}/estimate`) {
    return fixtureResponse("estimate");
  }

  return fixtureResponse("error-not_found", 404);
};
