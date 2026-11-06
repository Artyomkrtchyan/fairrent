import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";

const fixtures = JSON.parse(readFileSync(new URL("../../contracts/fixtures.json", import.meta.url), "utf8"));

async function setup(page, scenario) {
  await page.route("**/api/v1/**", route => {
    const path = new URL(route.request().url()).pathname;
    const key =
      path === "/api/v1/listings" ? scenario :
      path === "/api/v1/exchange-rate" ? "exchange-rate-stale" :
      path === "/api/v1/infrastructure" ? "infrastructure" :
      "error-not_found";
    const error = key.startsWith("error-");
    return route.fulfill({
      status: error ? (key === "error-service_unavailable" ? 503 : 404) : 200,
      contentType: "application/json",
      body: JSON.stringify(fixtures[key].value),
    });
  });
}

test("empty production-mode inventory has an explicit empty state", async ({ page }) => {
  await setup(page, "listings-empty");
  await page.goto("/");
  await expect(page.getByText("0 rentals found")).toBeVisible();
  await expect(page.getByText("No rentals available")).toBeVisible();
});

test("API failure is not silently replaced by example listings", async ({ page }) => {
  await setup(page, "error-service_unavailable");
  await page.goto("/");
  await expect(page.getByText("Listings unavailable")).toBeVisible();
  await expect(page.getByText("Synthetic apartment")).toHaveCount(0);
});

test("stale currency rate never enables AMD conversion", async ({ page }) => {
  await setup(page, "listings-empty");
  await page.goto("/");
  await expect(page.getByRole("button", { name: "AMD", exact: true })).toBeDisabled();
});
