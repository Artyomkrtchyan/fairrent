import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";

const data = JSON.parse(readFileSync(new URL("../../contracts/fixtures.json", import.meta.url), "utf8"));

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/**", (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const path = url.pathname;
    if (path === "/api/v1/listings/map") {
      // Map API returns a point array, not a listing-detail object.
      return route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
    }
    let key = "";
    if (path === "/api/v1/listings") {
      // Model server-side filtering. An incorrect/missing district query must not pass.
      const district = url.searchParams.get("district_id");
      key = district && district !== data.listings.value.items[0].district_id
        ? "listings-empty"
        : "listings";
    }
    else if (path.startsWith("/api/v1/listings/")) key = path.endsWith("/estimate") ? "estimate" : "listing-detail";
    else if (path === "/api/v1/valuations") {
      const body = JSON.parse(req.postData() || "{}");
      key = body.area_sqm && body.rooms ? "valuation" : "area-reference";
    }
    else if (path === "/api/v1/market-index") key = "market-index";
    else if (path === "/api/v1/infrastructure") key = "infrastructure";
    else if (path === "/api/v1/exchange-rate") key = "exchange-rate";
    else if (path === "/api/v1/reviews") key = "error-unauthenticated";
    else key = "error-not_found";
    return route.fulfill({
      status: key.startsWith("error-") ? 401 : 200,
      contentType: "application/json",
      body: JSON.stringify(data[key].value),
    });
  });
});

test("Browse renders a contract-backed listing and opens its details", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("1 rental found")).toBeVisible();
  await expect(page.getByText("Synthetic apartment").first()).toBeVisible();
  await page.getByText("View details").first().click();
  await expect(page).toHaveURL(/\/listings\//);
});

test("District filter reaches the listings API and changes results", async ({ page }) => {
  const listingRequests = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname === "/api/v1/listings") listingRequests.push(url);
  });

  await page.goto("/");
  await expect(page.getByText("1 rental found")).toBeVisible();
  await page.locator('input[list="catalogue-districts"]').fill("arabkir");
  await page.getByRole("button", { name: "Apply filters" }).click();

  await expect(page).toHaveURL(/district_id=arabkir/);
  await expect(page.getByText("0 rentals found")).toBeVisible();
  await expect(page.getByText("No rentals match your filters")).toBeVisible();
  await expect(page.getByText("Synthetic apartment")).toHaveCount(0);
  expect(listingRequests.some((url) => url.searchParams.get("district_id") === "arabkir")).toBe(true);
});

function statisticValue(page, label) {
  return page.locator("dt").filter({ hasText: new RegExp("^" + label + "$") }).locator("..").locator("dd");
}

test("Location form shows correct observed USD/m² statistics for both assessment types", async ({ page }) => {
  await page.goto("/valuation");
  await page.getByRole("button", { name: "Assess location" }).click();
  await expect(page.getByText("Area reference rent")).toBeVisible();
  await expect(statisticValue(page, "Mean rent per m²")).toContainText("12.00 USD");
  await expect(statisticValue(page, "Rent standard deviation per m²")).toContainText("2.00 USD");
  await expect(statisticValue(page, "Rent standard deviation per m²")).toContainText("/ month/m²");
  await page.getByLabel("Rooms").selectOption("2");
  await page.getByLabel(/Floor area/).fill("50");
  await page.getByRole("button", { name: "Assess location" }).click();
  await expect(page.getByText("Estimated rent")).toBeVisible();
  await expect(statisticValue(page, "Mean rent per m²")).toContainText("12.00 USD");
  await expect(statisticValue(page, "Rent standard deviation per m²")).toContainText("2.00 USD");
  await expect(statisticValue(page, "Rent standard deviation per m²")).not.toContainText("12.00 USD");
});

test("Sparse valuation marks unavailable per-square-metre statistics explicitly", async ({ page }) => {
  await page.route("**/api/v1/valuations", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(data["valuation-sparse"].value),
  }));
  await page.goto("/valuation");
  await page.getByRole("button", { name: "Assess location" }).click();
  await expect(statisticValue(page, "Mean rent per m²")).toHaveText("Not available");
  await expect(statisticValue(page, "Rent standard deviation per m²")).toHaveText("Not available");
  await expect(statisticValue(page, "Monthly rent standard deviation")).toHaveText("Not available");
});
test("Location form rejects invalid coordinates", async ({ page }) => {
  await page.goto("/valuation");
  await page.getByLabel("Latitude").fill("999");
  await page.getByRole("button", { name: "Assess location" }).click();
  await expect(page.getByRole("alert")).toContainText("valid latitude");
});

test("Map price legend uses real active listing snapshot when weekly index has no data", async ({ page }) => {
  const original = data.listings.value.items[0];
  const items = Array.from({ length: 5 }, (_, index) => ({
    ...original,
    id: `00000000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`,
    external_id: `listing-${index + 1}`,
    property_id: `property-${index + 1}`,
    dedup_group_id: null,
    district_id: "kentron",
    price_monthly_normalized: 500 + index * 40,
    area_sqm: 50,
  }));
  await page.route("**/api/v1/market-index*", (route) => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify(data["market-empty"].value),
  }));
  await page.route("**/api/v1/listings?*", (route) => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify({
      items, page: 1, page_size: 100, total: 5, has_more: false,
    }),
  }));
  await page.goto("/");
  await page.getByRole("button", { name: "Open district rent price guide" }).click();
  const legend = page.getByLabel("Area rent colour legend").first();
  await expect(legend.getByText("Active listings snapshot")).toBeVisible();
  await expect(legend.getByText(/Green: lower.*Yellow: middle.*Red: higher/)).toBeVisible();
  await expect(legend.getByText(/1 districts with ≥5 listings/)).toBeVisible();
});

test("Market analytics defaults to an actual listing snapshot", async ({ page }) => {
  await page.goto("/analytics");
  await expect(page.getByRole("heading", { name: "Market analytics" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Current listing snapshot" })).toBeVisible();
  await expect(page.getByText("600.00 USD").first()).toBeVisible();
  await page.getByRole("button", { name: "Table" }).click();
  const table = page.getByRole("table");
  await expect(table).toBeVisible();
  await expect(table.getByText("Kentron")).toBeVisible();
});

test("Market analytics has no weekly history control", async ({ page }) => {
  await page.goto("/analytics");
  await expect(page.getByRole("heading", { name: "Current listing snapshot" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Published weekly history" })).toHaveCount(0);
});

test("Reviewer workspace requires a session in real mode", async ({ page }) => {
  await page.goto("/reviews");
  await expect(page.getByRole("heading", { name: "Reviewer access" })).toBeVisible();
  await expect(page.getByLabel("Reviewer session token")).toBeVisible();
  await expect(page.getByText("Synthetic apartment")).toHaveCount(0);
});

test("Mobile navigation and filter controls remain usable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "Show filters" }).click();
  await expect(page.locator('input[list="catalogue-districts"]')).toBeVisible();
  await page.getByRole("button", { name: "Menu" }).click();
  await expect(page.getByRole("link", { name: "Market analytics" })).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(page.locator(":focus")).toBeVisible();
});
