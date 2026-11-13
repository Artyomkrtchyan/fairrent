import type { getListingDetails } from "@/api/listings";
import { apiMode } from "@/api/client";
import { formatListingRent } from "@/lib/listing-rent";
import { safeExternalUrl } from "@/lib/safe-external-url";

type Listing = Awaited<ReturnType<typeof getListingDetails>>["listing"];

export function ListingSource({ listing }: { listing: Listing }) {
  const sourceUrl = safeExternalUrl(listing.source_url);

  const originalPrice =
    listing.price_original !== null && listing.currency_original !== null
      ? `${listing.currency_original === "USD" || listing.currency_original === "AMD"
          ? formatListingRent(listing.price_original, listing.currency_original)
          : `${new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(listing.price_original)} ${listing.currency_original}`} / month`
      : "Not available";

  return (
    <section className="card-surface p-5" aria-labelledby="listing-source-title">
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
      {/* Listing freshness is part of the source card. */}
      <div className="mt-5 border-t pt-4 text-sm" aria-label="Listing freshness">
        <h3 className="font-semibold">Listing freshness</h3>
        <p className="mt-2 text-muted-foreground">
          Last seen:{" "}
          <time dateTime={listing.last_seen_at}>
            {new Date(listing.last_seen_at).toLocaleString("en-GB", {
              timeZone: "Asia/Yerevan",
            })}
          </time>
        </p>
        {listing.freshness.is_stale && (
          <p className="mt-3 rounded-md border p-3 text-muted-foreground">
            This listing’s source data is marked stale. Check the date before relying on it.
          </p>
        )}
      </div>
    </section>
  );
}
