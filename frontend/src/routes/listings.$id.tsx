import { createFileRoute, Link, notFound } from "@tanstack/react-router";

import { getListingDetails, ListingApiError } from "@/api/listings";

import { apiMode } from "@/api/client";
import { Money, RateNote } from "@/components/ui-bits";

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
  const { listing, signals } = Route.useLoaderData();

  const title = listing.title || "Apartment in Yerevan";

  return (
    <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
      <Link to="/" className="text-sm font-semibold text-primary">
        ← Back to rentals
      </Link>

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

      <div className="mt-6 grid gap-4 md:grid-cols-3">
        <section className="card-surface p-5 md:col-span-2">
          <h2 className="text-xl font-semibold">Property information</h2>

          <dl className="mt-4 grid grid-cols-2 gap-4 text-sm">
            <div>
              <dt className="text-muted-foreground">District</dt>
              <dd>{listing.district_id ?? "Not available"}</dd>
            </div>

            <div>
              <dt className="text-muted-foreground">Rooms</dt>
              <dd>{listing.rooms ?? "Not available"}</dd>
            </div>

            <div>
              <dt className="text-muted-foreground">Area</dt>
              <dd>{listing.area_sqm === null ? "Not available" : `${listing.area_sqm} m²`}</dd>
            </div>

            <div>
              <dt className="text-muted-foreground">Floor</dt>
              <dd>{listing.floor ?? "Not available"}</dd>
            </div>
          </dl>

          <h3 className="mt-6 font-sans text-sm font-bold">Description</h3>

          <p className="mt-2 whitespace-pre-wrap text-sm">
            {listing.description ?? "Description unavailable."}
          </p>
        </section>

        <aside className="card-surface p-5" aria-label="Asking rent and freshness">
          <h2 className="text-sm font-semibold text-muted-foreground">Monthly asking rent</h2>

          <p className="mt-3 text-2xl font-bold text-heading">
            {listing.price_monthly_normalized === null ? (
              "Rent unavailable"
            ) : (
              <Money usd={listing.price_monthly_normalized} suffix="/ month" />
            )}
          </p>

          <div className="mt-3">
            <RateNote />
          </div>

          <p className="mt-5 text-sm">
            Last seen:{" "}
            <time dateTime={listing.last_seen_at}>
              {new Date(listing.last_seen_at).toLocaleDateString("en-GB", {
                timeZone: "Asia/Yerevan",
              })}
            </time>
          </p>

          {listing.freshness.is_stale && (
            <p className="mt-3 rounded-md border p-3 text-sm">
              Source data is marked stale. Check its date before relying on this information.
            </p>
          )}
        </aside>
      </div>

      <section className="card-surface mt-4 p-5">
        <h2 className="text-xl font-semibold">Valuation and risk evidence</h2>

        <p className="mt-2 text-sm text-muted-foreground">
          Full valuation and evidence presentation follows in D04. High asking rent alone does not
          establish fraud.
        </p>

        <p className="mt-3 text-sm">
          Linked signals in this response: {signals.length}. Their evidence is not evaluated by this
          preview.
        </p>
      </section>
    </main>
  );
}
