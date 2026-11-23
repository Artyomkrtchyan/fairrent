import Decimal from "decimal.js-light";

export type RentCurrency = "USD" | "AMD";

export interface ListingPrice {
  price_original: number | null;
  currency_original: string | null;
  price_monthly_normalized: number | null;
}

export interface DisplayRent {
  amount: number;
  currency: RentCurrency;
  // For comparison with the USD-denominated estimate.
  askingUsd: number | null;
}

// The source advertisement is authoritative for what the owner is asking.
// The normalized USD field can reflect the exchange rate on the ingestion date.
export function resolveListingRent(
  listing: ListingPrice,
  preferredCurrency: RentCurrency,
  amdPerUsd: number | null,
): DisplayRent | null {
  const rate = amdPerUsd !== null && Number.isFinite(amdPerUsd) && amdPerUsd > 0 ? amdPerUsd : null;
  const original = listing.price_original;
  const originalCurrency = listing.currency_original;

  if (
    original !== null &&
    Number.isFinite(original) &&
    original >= 0 &&
    (originalCurrency === "USD" || originalCurrency === "AMD")
  ) {
    const askingUsd =
      originalCurrency === "USD"
        ? original
        : rate !== null
          ? new Decimal(original).div(rate).toNumber()
          : null;

    if (preferredCurrency === originalCurrency || rate === null) {
      return { amount: original, currency: originalCurrency, askingUsd };
    }

    const converted =
      originalCurrency === "AMD"
        ? new Decimal(original).div(rate).toNumber()
        : new Decimal(original).times(rate).toNumber();

    return { amount: converted, currency: preferredCurrency, askingUsd };
  }

  // Missing source price: fall back to the explicitly normalized USD field.
  const normalized = listing.price_monthly_normalized;
  if (normalized === null || !Number.isFinite(normalized) || normalized < 0) return null;
  if (preferredCurrency === "AMD" && rate !== null) {
    return {
      amount: new Decimal(normalized).times(rate).toNumber(),
      currency: "AMD",
      askingUsd: normalized,
    };
  }
  return { amount: normalized, currency: "USD", askingUsd: normalized };
}

export function formatListingRent(amount: number, currency: RentCurrency): string {
  return `${new Intl.NumberFormat("en-US", {
    minimumFractionDigits: currency === "USD" ? 2 : 0,
    maximumFractionDigits: 2,
  }).format(amount)} ${currency}`;
}
