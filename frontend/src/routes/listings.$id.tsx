import { ListingSource } from "@/components/ListingSource";

import { PropertyPhoto } from "@/components/PropertyPhoto";

import { RiskEvidence } from "@/components/RiskEvidence";

import { MarketAssessment } from "@/components/MarketAssessment";

import { createFileRoute, Link, notFound, useRouter, useRouterState } from "@tanstack/react-router";

import { getListingDetails, ListingApiError } from "@/api/listings";

import { apiMode } from "@/api/client";

export const Route = createFileRoute("/listings/$id")({
  loader: async ({ params, abortController }) => {
    try {
      return await getListingDetails(params.id, abortController.signal);
    } catch (error) {
      if (error instanceof ListingApiError && error.status === 404) {
        throw notFound();
      }

      throw error;
    }
  },

  pendingComponent: () => (
    <main className="mx-auto max-w-5xl px-4 py-12">
      <p role="status">Loading listing details…</p>
    </main>
  ),

  component: ListingPage,
});

function ListingPage() {
  const router = useRouter();

  const fromCatalogue = useRouterState({
    select: (state) => state.location.state.fromCatalogue === true,
  });

  const { listing, signals, estimate } = Route.useLoaderData();

  const title = listing.title || "Apartment in Yerevan";

  return (
    <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
      {fromCatalogue ? (
        <button
          type="button"
          onClick={() => router.history.back()}
          className="text-sm font-semibold text-primary"
        >
          ← Back to rentals
        </button>
      ) : (
        <Link to="/" className="text-sm font-semibold text-primary">
          ← Browse rentals
        </Link>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        {apiMode === "mock" && (
          <span className="rounded-full border px-3 py-1 text-xs">Synthetic C01 example</span>
        )}

        {listing.status === "inactive" && (
          <span className="rounded-full border px-3 py-1 text-xs">Inactive — no longer listed</span>
        )}
      </div>

      <h1 className="mt-4 text-3xl font-semibold sm:text-4xl">{title}</h1>

      <p className="mt-2 text-muted-foreground">{listing.address ?? "Address unavailable"}</p>
      <PropertyPhoto key={listing.id} url={listing.thumbnail_url} title={title} />

      <div className="mt-6 grid items-start gap-6 lg:grid-cols-2">
        <section className="card-surface p-5" aria-labelledby="property-information-title">
          <h2 id="property-information-title" className="text-xl font-semibold">
            Property information
          </h2>

          <dl className="mt-4 grid grid-cols-2 gap-5 text-sm">
            <div>
              <dt className="text-muted-foreground">District</dt>
              <dd className="mt-1 font-semibold">{listing.district_id ?? "Not available"}</dd>
            </div>

            <div>
              <dt className="text-muted-foreground">Rooms</dt>
              <dd className="mt-1 font-semibold">{listing.rooms ?? "Not available"}</dd>
            </div>

            <div>
              <dt className="text-muted-foreground">Area</dt>
              <dd className="mt-1 font-semibold">
                {listing.area_sqm === null ? "Not available" : `${listing.area_sqm} m²`}
              </dd>
            </div>

            <div>
              <dt className="text-muted-foreground">Floor</dt>
              <dd className="mt-1 font-semibold">{listing.floor ?? "Not available"}</dd>
            </div>

            <div>
              <dt className="text-muted-foreground">Floors in building</dt>
              <dd className="mt-1 font-semibold">{listing.total_floors ?? "Not available"}</dd>
            </div>

            <div>
              <dt className="text-muted-foreground">Utilities included</dt>
              <dd className="mt-1 font-semibold">
                {listing.utilities_included === null
                  ? "Not available"
                  : listing.utilities_included
                    ? "Yes"
                    : "No"}
              </dd>
            </div>

            <div>
              <dt className="text-muted-foreground">Renovation</dt>
              <dd className="mt-1 font-semibold">{listing.renovation ?? "Not available"}</dd>
            </div>

            <div>
              <dt className="text-muted-foreground">Building type</dt>
              <dd className="mt-1 font-semibold">
                {listing.building_type ?? listing.building_type_raw ?? "Not available"}
              </dd>
            </div>
          </dl>

          <div className="mt-6 border-t pt-5">
            <h3 className="font-sans text-sm font-bold">Description</h3>

            <p className="mt-2 whitespace-pre-wrap break-words text-sm">
              {listing.description ?? "Description unavailable."}
            </p>
          </div>
        </section>
        <div className="space-y-4">
          <MarketAssessment askingUsd={listing.price_monthly_normalized} estimate={estimate} />

          <section className="card-surface p-5 text-sm" aria-label="Listing freshness">
            <h2 className="font-sans font-bold">Listing freshness</h2>

            <p className="mt-3">
              Last seen:{" "}
              <time dateTime={listing.last_seen_at}>
                {new Date(listing.last_seen_at).toLocaleString("en-GB", {
                  timeZone: "Asia/Yerevan",
                })}
              </time>
            </p>

            {listing.freshness.is_stale && (
              <p className="mt-3 rounded-md border p-3">
                This listing’s source data is marked stale. Check the date before relying on it.
              </p>
            )}
          </section>
        </div>
      </div>
      <ListingSource listing={listing} />

      <RiskEvidence signals={signals} />
    </main>
  );
}
