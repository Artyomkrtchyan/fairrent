import type { getListingDetails } from "@/api/listings";
import { apiMode } from "@/api/client";

type Listing = Awaited<ReturnType<typeof getListingDetails>>["listing"];

function safeSourceUrl(value: string): string | null {
  try {
    const url = new URL(value);

    if ((url.protocol !== "https:" && url.protocol !== "http:") || url.username || url.password) {
      return null;
    }

    return url.href;
  } catch {
    return null;
  }
}

export function ListingSource({ listing }: { listing: Listing }) {
  const sourceUrl = safeSourceUrl(listing.source_url);

  const originalPrice =
    listing.price_original !== null && listing.currency_original !== null
      ? `${new Intl.NumberFormat("en-US", {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        }).format(listing.price_original)} ${listing.currency_original} / month`
      : "Not available";

  return (
    <section className="card-surface mt-6 p-5" aria-labelledby="listing-source-title">
      <h2 id="listing-source-title" className="text-xl font-semibold">
        Listing source
      </h2>

      <dl className="mt-4 grid gap-4 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-muted-foreground">Source</dt>
          <dd className="mt-1 font-semibold">{listing.source}</dd>
        </div>

        <div>
          <dt className="text-muted-foreground">Original asking rent</dt>
          <dd className="mt-1 font-semibold">{originalPrice}</dd>
        </div>
      </dl>

      <p className="mt-3 text-xs text-muted-foreground">
        The original amount and currency are preserved. They do not change with the display-currency
        selector.
      </p>

      {apiMode === "mock" && (
        <p className="mt-3 text-sm text-muted-foreground">
          This is a synthetic example. Its source URL is a demonstration link, not a real apartment
          advertisement.
        </p>
      )}

      {sourceUrl ? (
        <a
          href={sourceUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-4 inline-flex rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground"
        >
          {apiMode === "mock" ? "Open demonstration source" : "Open original listing"}
          <span className="ml-2" aria-hidden="true">
            ↗
          </span>
          <span className="sr-only"> — opens in a new tab</span>
        </a>
      ) : (
        <p className="mt-4 text-sm text-muted-foreground">No usable source link was supplied.</p>
      )}
    </section>
  );
}
