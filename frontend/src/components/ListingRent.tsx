import { usePrefs } from "@/lib/prefs";
import { formatListingRent, resolveListingRent, type ListingPrice } from "@/lib/listing-rent";

export function ListingRent({
  listing,
  suffix = "/ month",
}: {
  listing: ListingPrice;
  suffix?: string;
}) {
  const { currency, amdPerUsd } = usePrefs();
  const rent = resolveListingRent(listing, currency, amdPerUsd);

  if (!rent) return <>Rent unavailable</>;

  return (
    <span className="tabular-nums">
      {formatListingRent(rent.amount, rent.currency)}
      {suffix && <span className="text-muted-foreground text-[0.8em] font-normal"> {suffix}</span>}
    </span>
  );
}
