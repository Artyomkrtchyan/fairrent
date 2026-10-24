import type { components } from "@/api/schema";

export type MapListing = components["schemas"]["Listing"];

/** Never invent a location from an address or district centroid. */
export function hasMapCoordinates(listing: MapListing): boolean {
  return (
    listing.coordinate_confidence !== "unknown" &&
    typeof listing.latitude === "number" &&
    Number.isFinite(listing.latitude) &&
    typeof listing.longitude === "number" &&
    Number.isFinite(listing.longitude) &&
    listing.latitude >= -90 &&
    listing.latitude <= 90 &&
    listing.longitude >= -180 &&
    listing.longitude <= 180
  );
}
