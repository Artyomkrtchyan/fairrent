import { describe, expect, it } from "vitest";
import { formatListingRent, resolveListingRent } from "@/lib/listing-rent";

describe("listing asking rent uses the source advertisement", () => {
  const amdListing = {
    price_original: 290_000,
    currency_original: "AMD",
    price_monthly_normalized: 678.565, // ingestion-date USD equivalent, not today's rate
  };

  it("preserves the original AMD amount with AMD selected", () => {
    const rent = resolveListingRent(amdListing, "AMD", 400);
    expect(rent).toMatchObject({ amount: 290_000, currency: "AMD", askingUsd: 725 });
    expect(formatListingRent(rent!.amount, rent!.currency)).toBe("290,000 AMD");
  });

  it("converts original AMD into USD using the current available rate", () => {
    const rent = resolveListingRent(amdListing, "USD", 400);
    expect(rent).toMatchObject({ amount: 725, currency: "USD", askingUsd: 725 });
    expect(formatListingRent(rent!.amount, rent!.currency)).toBe("725.00 USD");
  });

  it("uses the unchanged source USD when selected, and current rate for AMD", () => {
    const listing = { price_original: 800, currency_original: "USD", price_monthly_normalized: 800 };
    expect(resolveListingRent(listing, "USD", 400)).toMatchObject({ amount: 800, currency: "USD" });
    expect(resolveListingRent(listing, "AMD", 400)).toMatchObject({ amount: 320_000, currency: "AMD" });
  });

  it("does not fabricate a conversion without a valid current rate", () => {
    expect(resolveListingRent(amdListing, "USD", null)).toMatchObject({
      amount: 290_000,
      currency: "AMD",
      askingUsd: null,
    });
    expect(resolveListingRent(amdListing, "USD", 0)?.currency).toBe("AMD");
  });

  it("falls back to normalized USD only if the source amount is missing", () => {
    const rent = resolveListingRent({
      price_original: null,
      currency_original: null,
      price_monthly_normalized: 700,
    }, "AMD", 400);
    expect(rent).toMatchObject({ amount: 280_000, currency: "AMD", askingUsd: 700 });
  });

  it("does not invent prices when no usable source or normalized amount exists", () => {
    expect(resolveListingRent({
      price_original: null,
      currency_original: null,
      price_monthly_normalized: null,
    }, "USD", null)).toBeNull();
  });
});
