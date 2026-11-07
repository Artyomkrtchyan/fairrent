import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";

const fixtures = JSON.parse(readFileSync(new URL("../../contracts/fixtures.json", import.meta.url), "utf8"));

const sourceListing = {
  ...fixtures.listings.value.items[0],
  price_original: 290000,
  currency_original: "AMD",
  price_monthly_normalized: 678.565,
  conversion: { rate_to_usd: 0.00234, rate_date: "2026-10-17", rate_source: "historical-test" },
};

test("catalogue and detail asking rent respect source currency and today's display rate", async ({ page }) => {
  await page.route("**/api/v1/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    let response;
    if (path === "/api/v1/listings/map") response = [];
    else if (path === "/api/v1/listings") response = { ...fixtures.listings.value, items: [sourceListing] };
    else if (path.startsWith("/api/v1/listings/")) response = {
      ...fixtures["listing-detail"].value,
      listing: sourceListing,
    };
    else if (path === "/api/v1/exchange-rate") response = fixtures["exchange-rate"].value;
    else if (path === "/api/v1/infrastructure") response = fixtures.infrastructure.value;
    else response = fixtures["error-not_found"].value;

    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(response) });
  });

  await page.goto("/");
  await expect(page.getByText("725.00 USD", { exact: false }).first()).toBeVisible();
  await expect(page.getByText(/678\.57 USD/)).toHaveCount(0);
  await page.getByRole("button", { name: "AMD", exact: true }).click();
  await expect(page.getByText("290,000 AMD", { exact: false }).first()).toBeVisible();

  await page.getByText("View details").first().click();
  const asking = page.locator("dt").filter({ hasText: /^Asking rent$/ }).locator("..").locator("dd");
  await expect(asking).toContainText("290,000 AMD");
  const original = page.locator("dt").filter({ hasText: /^Original asking rent$/ }).locator("..").locator("dd");
  await expect(original).toHaveText("290,000 AMD / month");

  await page.getByRole("button", { name: "USD", exact: true }).click();
  await expect(asking).toContainText("725.00 USD");
  await expect(original).toHaveText("290,000 AMD / month");
});
