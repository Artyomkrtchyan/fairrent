import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";

const data = JSON.parse(readFileSync(new URL("../../contracts/fixtures.json", import.meta.url), "utf8"));

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/**", (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    let key = "";
    if (path === "/api/v1/listings") key = "listings";
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

test("Browse and filters render a contract-backed listing", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("1 rental found")).toBeVisible();
  await expect(page.getByText("Synthetic apartment").first()).toBeVisible();
  await page.locator('input[list="catalogue-districts"]').fill("kentron");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect(page).toHaveURL(/district_id=kentron/);
  await page.getByText("View details").first().click();
  await expect(page).toHaveURL(/\/listings\//);
});

test("Location form uses coordinate and property assessments", async ({ page }) => {
  await page.goto("/valuation");
  await page.getByRole("button", { name: "Assess location" }).click();
  await expect(page.getByText("Area reference rent")).toBeVisible();
  await page.getByLabel("Rooms").selectOption("2");
  await page.getByLabel(/Floor area/).fill("50");
  await page.getByRole("button", { name: "Assess location" }).click();
  await expect(page.getByText("Estimated rent")).toBeVisible();
});

test("Location form rejects invalid coordinates", async ({ page }) => {
  await page.goto("/valuation");
  await page.getByLabel("Latitude").fill("999");
  await page.getByRole("button", { name: "Assess location" }).click();
  await expect(page.getByRole("alert")).toContainText("valid latitude");
});

test("Market analytics shows the weekly data table", async ({ page }) => {
  await page.goto("/analytics");
  await expect(page.getByRole("heading", { name: "Market analytics" })).toBeVisible();
  await page.getByRole("button", { name: "Table" }).click();
  await expect(page.getByRole("table")).toBeVisible();
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
