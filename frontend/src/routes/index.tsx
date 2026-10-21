import { CatalogueFilters } from "@/components/CatalogueFilters";

import { usePrefs } from "@/lib/prefs";

import { createFileRoute, Link, type SearchSchemaInput } from "@tanstack/react-router";

import { parseCatalogueSearch, type CatalogueSearch } from "@/lib/catalogue-search";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Money, RateNote } from "@/components/ui-bits";

import { SkylineHero } from "@/components/SkylineHero";
import { ListingPhoto } from "@/components/ListingPhoto";
import { getListings } from "@/api/listings";
import { apiMode } from "@/api/client";
import type { components } from "@/api/schema";

type Listing = components["schemas"]["Listing"];

export const Route = createFileRoute("/")({
  validateSearch: (search: SearchSchemaInput & Partial<CatalogueSearch>) =>
    parseCatalogueSearch(search),

  component: Browse,
});

const priceLabels = {
  within_range: "Within estimated range",
  above_range: "Above estimated range",
  below_range: "Below estimated range",
  insufficient_data: "Estimate unavailable",
};

const priceColors = {
  within_range: "bg-within/15 text-within",
  above_range: "bg-amber-100 text-amber-900",
  below_range: "bg-blue-100 text-blue-900",
  insufficient_data: "bg-muted text-muted-foreground",
};

function formatRent(amount: number | null): string {
  if (amount === null) {
    return "Rent unavailable";
  }

  return `${new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount)} USD / month`;
}

function Browse() {
  const search = Route.useSearch();
  const { format } = usePrefs();

  const activeFilters: {
    key: "district_id" | "rooms" | "price_min" | "price_max" | "area_min" | "area_max";
    label: string;
  }[] = [];

  if (search.district_id !== undefined) {
    activeFilters.push({
      key: "district_id",
      label: `District: ${search.district_id}`,
    });
  }

  if (search.rooms !== undefined) {
    activeFilters.push({
      key: "rooms",
      label: `Rooms: ${search.rooms}`,
    });
  }

  if (search.price_min !== undefined) {
    activeFilters.push({
      key: "price_min",
      label: `Min rent: ${format(search.price_min)}`,
    });
  }

  if (search.price_max !== undefined) {
    activeFilters.push({
      key: "price_max",
      label: `Max rent: ${format(search.price_max)}`,
    });
  }

  if (search.area_min !== undefined) {
    activeFilters.push({
      key: "area_min",
      label: `Min area: ${search.area_min} m²`,
    });
  }

  if (search.area_max !== undefined) {
    activeFilters.push({
      key: "area_max",
      label: `Max area: ${search.area_max} m²`,
    });
  }
  const navigate = Route.useNavigate();

  const [filterRevision, setFilterRevision] = useState(0);

  function applyFilters(next: CatalogueSearch) {
    setFilterRevision((value) => value + 1);

    void navigate({
      search: next,
      resetScroll: false,
    });
  }
  const [view, setView] = useState<"list" | "map">("list");

  const { data, isPending, isError, isFetching, refetch } = useQuery({
    queryKey: ["listings", apiMode, search],
    queryFn: ({ signal }) => getListings(signal, search),
    retry: false,
  });

  return (
    <main>
      <SkylineHero>
        <span className="inline-flex rounded-md bg-hero-foreground/15 px-2 py-1 text-xs font-bold">
          {apiMode === "mock" ? "Synthetic C01 examples" : "Long-term apartments"}
        </span>
        <h1 className="mt-3 max-w-2xl text-4xl font-semibold text-hero-foreground sm:text-5xl">
          A clearer view of your next home.
        </h1>

        <p className="mt-2 text-sm text-muted-foreground">
          Catalogue filters and sorting follow in D03. Prices use the selected display currency;
          underlying amounts remain in USD.
        </p>
        <div className="mt-2">
          <RateNote />
        </div>
      </SkylineHero>

      <div className="mx-auto -mt-12 max-w-7xl px-4 sm:px-6">
        <CatalogueFilters
          key={`${JSON.stringify(search)}-${filterRevision}`}
          search={search}
          onApply={applyFilters}
        />

        {activeFilters.length > 0 && (
          <div aria-label="Active filters" className="mt-3 flex flex-wrap gap-2">
            {activeFilters.map((filter) => (
              <button
                key={filter.key}
                type="button"
                aria-label={`Remove filter: ${filter.label}`}
                onClick={() => {
                  const next = {
                    ...search,
                    page: 1,
                  };

                  delete next[filter.key];

                  setFilterRevision((value) => value + 1);

                  void navigate({
                    search: next,
                    resetScroll: false,
                  });
                }}
                className="inline-flex items-center gap-2 rounded-full border bg-card px-3 py-2 text-xs font-semibold hover:border-primary"
              >
                {filter.label}
                <span aria-hidden="true">×</span>
              </button>
            ))}
            <button
              type="button"
              onClick={() =>
                applyFilters({
                  page: 1,
                  page_size: search.page_size,
                  sort: search.sort,
                  status: "active",
                })
              }
              className="rounded-full border px-3 py-2 text-xs font-semibold hover:border-primary"
            >
              Clear all
            </button>
          </div>
        )}

        <div className="mt-3">
          <RateNote />
        </div>

        <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm" aria-live="polite">
            {isPending
              ? "Loading listings…"
              : isError
                ? "Listings unavailable"
                : `${data?.total ?? 0} ${data?.total === 1 ? "rental" : "rentals"} found`}
          </p>

          {isFetching && !isPending && (
            <span role="status" className="text-sm text-muted-foreground">
              Updating results…
            </span>
          )}

          <label className="flex items-center gap-2 text-sm">
            <span className="font-semibold">Sort by</span>

            <select
              value={search.sort}
              onChange={(event) => {
                const sort = event.target.value;

                if (
                  sort === "newest" ||
                  sort === "price_asc" ||
                  sort === "price_desc" ||
                  sort === "area_asc" ||
                  sort === "area_desc"
                ) {
                  void navigate({
                    search: {
                      ...search,
                      sort,
                      page: 1,
                    },
                    resetScroll: false,
                  });
                }
              }}
              className="rounded-md border bg-card px-3 py-2"
            >
              <option value="newest">Newest first</option>
              <option value="price_asc">Rent: low to high</option>
              <option value="price_desc">Rent: high to low</option>
              <option value="area_asc">Area: small to large</option>
              <option value="area_desc">Area: large to small</option>
            </select>
          </label>

          <div
            role="group"
            aria-label="Results view"
            className="flex rounded-md border p-1 text-xs font-semibold lg:hidden"
          >
            {(["list", "map"] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                aria-pressed={view === mode}
                onClick={() => setView(mode)}
                className={`rounded px-3 py-2 capitalize ${
                  view === mode ? "bg-primary text-primary-foreground" : "text-muted-foreground"
                }`}
              >
                {mode}
              </button>
            ))}
          </div>
        </div>

        {isPending && (
          <div className="card-surface mt-4 p-6" role="status">
            Loading rental information…
          </div>
        )}

        {isError && (
          <section className="card-surface mt-4 p-6" role="alert">
            <h2 className="text-lg font-semibold">We couldn’t load listings.</h2>

            <p className="mt-2 text-sm text-muted-foreground">
              Check the API connection and try again. Real API errors are never replaced with demo
              results.
            </p>

            <button
              type="button"
              disabled={isFetching}
              onClick={() => void refetch()}
              className="mt-4 rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-50"
            >
              {isFetching ? "Retrying…" : "Retry"}
            </button>
          </section>
        )}

        {data && !isError && (
          <>
            {data.has_more && (
              <p className="mt-4 rounded-md border p-3 text-sm">
                This response contains only part of the results. Pagination follows in D03.
              </p>
            )}

            <div className="mt-4 grid gap-6 lg:grid-cols-2">
              <ul className={`${view === "list" ? "grid" : "hidden"} content-start gap-3 lg:grid`}>
                {data.items.length === 0 && (
                  <li className="card-surface p-6">
                    <h3 className="font-sans text-base font-bold">
                      {search.page > 1
                        ? "No rentals on this page"
                        : activeFilters.length > 0
                          ? "No rentals match your filters"
                          : "No rentals available"}
                    </h3>

                    <p className="mt-2 text-sm text-muted-foreground">
                      {search.page > 1
                        ? "Return to the first page to see the available results."
                        : activeFilters.length > 0
                          ? "Try a wider rent or area range, or clear your filters."
                          : "Please check again later."}
                    </p>

                    {activeFilters.length > 0 && (
                      <button
                        type="button"
                        onClick={() =>
                          applyFilters({
                            page: 1,
                            page_size: search.page_size,
                            sort: search.sort,
                            status: "active",
                          })
                        }
                        className="mt-4 rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground"
                      >
                        Clear filters
                      </button>
                    )}
                  </li>
                )}

                {data.items.map((listing) => (
                  <ListingCard key={listing.id} listing={listing} />
                ))}
              </ul>

              <aside
                aria-label="Future map view"
                className={`${
                  view === "map" ? "flex" : "hidden"
                } card-surface min-h-80 flex-col justify-center p-8 text-center lg:flex`}
              >
                <p className="text-xs font-bold uppercase tracking-widest text-primary">
                  Map preview
                </p>

                <h2 className="mt-3 text-2xl font-semibold">Explore the neighborhood.</h2>

                <p className="mx-auto mt-3 max-w-sm text-sm text-muted-foreground">
                  The interactive map and infrastructure layers follow in D05. This panel does not
                  represent listing locations or map coverage.
                </p>
              </aside>
            </div>

            <nav
              aria-label="Listing pages"
              className="mt-6 flex flex-wrap items-center justify-center gap-4"
            >
              <button
                type="button"
                disabled={search.page <= 1 || isFetching}
                onClick={() => {
                  void navigate({
                    search: {
                      ...search,
                      page: search.page - 1,
                    },
                  });
                }}
                className="rounded-md border px-4 py-2 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-40"
              >
                Previous
              </button>

              <span className="text-sm" aria-live="polite">
                Page {search.page} · {data.total} matching rentals
              </span>

              <button
                type="button"
                disabled={!data.has_more || isFetching}
                onClick={() => {
                  void navigate({
                    search: {
                      ...search,
                      page: search.page + 1,
                    },
                  });
                }}
                className="rounded-md border px-4 py-2 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-40"
              >
                Next
              </button>
            </nav>

            {data.items.length === 0 && search.page > 1 && (
              <div className="mt-3 text-center">
                <p className="text-sm text-muted-foreground">There are no listings on this page.</p>

                <button
                  type="button"
                  onClick={() => {
                    void navigate({
                      search: {
                        ...search,
                        page: 1,
                      },
                    });
                  }}
                  className="mt-2 rounded-md border px-4 py-2 text-sm font-semibold"
                >
                  Return to first page
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </main>
  );
}

function ListingCard({ listing }: { listing: Listing }) {
  const title = listing.title || "Apartment in Yerevan";
  const status = listing.price_status ?? "insufficient_data";

  return (
    <li>
      <Link
        to="/listings/$id"
        params={{ id: listing.id }}
        state={{ fromCatalogue: true }}
        className="card-surface block overflow-hidden transition hover:border-primary"
      >
        <ListingPhoto photoKey={null} title={title} size="card" />

        <div className="p-4">
          <h3 className="font-sans text-base font-bold">{title}</h3>

          <p className="mt-1 text-xs text-muted-foreground">
            {listing.district_id ?? "District unavailable"}
            {" · "}
            {listing.rooms === null ? "Rooms unavailable" : `${listing.rooms} rooms`}
            {" · "}
            {listing.area_sqm === null ? "Area unavailable" : `${listing.area_sqm} m²`}
          </p>

          <p className="mt-3 text-lg font-bold text-heading">
            {listing.price_monthly_normalized === null ? (
              "Rent unavailable"
            ) : (
              <Money usd={listing.price_monthly_normalized} suffix="/ month" />
            )}
          </p>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className={`rounded-full px-3 py-1 text-xs font-semibold ${priceColors[status]}`}>
              {priceLabels[status]}
            </span>

            {listing.status === "inactive" && (
              <span className="rounded-full border px-3 py-1 text-xs">Inactive</span>
            )}

            {apiMode === "mock" && (
              <span className="rounded-full border px-3 py-1 text-xs">Synthetic example</span>
            )}
          </div>

          <p className="mt-3 text-xs text-muted-foreground">
            Last seen:{" "}
            <time dateTime={listing.last_seen_at}>
              {new Date(listing.last_seen_at).toLocaleDateString("en-GB", {
                timeZone: "Asia/Yerevan",
              })}
            </time>
          </p>

          {listing.freshness.is_stale && (
            <p className="mt-2 text-sm">Source data is marked stale.</p>
          )}

          <p className="mt-4 text-sm font-semibold text-primary">View details →</p>
        </div>
      </Link>
    </li>
  );
}
