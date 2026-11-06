import { mockInfrastructurePage } from "./mock-infrastructure";
import fixtures from "../../../contracts/fixtures.json";
import { mockListingPage } from "./mock-listings";
import { mockMarketPage } from "./mock-market";

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
 * Supports bounded catalogue/place fixture filters, but not authentication or database writes.
 */
export const mockFetch: typeof fetch = async (input, init) => {
  const request = new Request(input, init);

  if (request.signal.aborted) {
    throw new DOMException("Request aborted", "AbortError");
  }

  const { pathname } = new URL(request.url);

  if (request.method === "POST" && pathname === "/api/v1/valuations") {
    const body = (await request.json()) as { area_sqm?: number; rooms?: number };
    return fixtureResponse(body.area_sqm && body.rooms ? "valuation" : "area-reference");
  }
  if (request.method !== "GET") {
    return fixtureResponse("error-service_unavailable", 503);
  }

  switch (pathname) {
    case "/api/v1/listings/map":
      return Response.json(
        mockListingPage(new URL(request.url), true).items.flatMap((listing) =>
          listing.latitude === null ||
          listing.longitude === null ||
          listing.coordinate_confidence === "unknown"
            ? []
            : [
                {
                  id: listing.id,
                  latitude: listing.latitude,
                  longitude: listing.longitude,
                  coordinate_confidence: listing.coordinate_confidence,
                },
              ],
        ),
      );

    case "/api/v1/listings":
      return new Response(JSON.stringify(mockListingPage(new URL(request.url))), {
        status: 200,
        headers: {
          "Content-Type": "application/json",
        },
      });

    case "/api/v1/exchange-rate":
      return fixtureResponse("exchange-rate");

    case "/api/v1/market-index": {
      const page = mockMarketPage(new URL(request.url));

      if (!page) {
        return fixtureResponse("error-validation_error", 422);
      }

      return new Response(JSON.stringify(page), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    case "/api/v1/infrastructure": {
      const page = mockInfrastructurePage(new URL(request.url));
      if (!page) return fixtureResponse("error-validation_error", 422);
      return new Response(JSON.stringify(page), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

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
