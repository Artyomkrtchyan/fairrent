import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";

const fixtures = JSON.parse(readFileSync(new URL("../../contracts/fixtures.json", import.meta.url), "utf8"));
const json = (route, value) => route.fulfill({
  status: 200, contentType: "application/json", body: JSON.stringify(value),
});

test("controlled reviewer workflow saves one decision and shows server history", async ({ page }) => {
  let review = fixtures.reviews.value.items[0];
  const decisions = [];
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === "/api/v1/exchange-rate")
      return json(route, fixtures["exchange-rate"].value);
    if (url.pathname === "/api/v1/reviews" && request.method() === "GET")
      return json(route, { items: [review], total: 1, page: 1, page_size: 20, has_more: false });
    if (url.pathname.startsWith("/api/v1/reviews/") && request.method() === "PATCH") {
      const input = JSON.parse(request.postData() || "{}");
      decisions.push(input);
      review = {
        ...fixtures["review-resolved"].value,
        status: input.status, decision: input.decision, reason: input.reason,
        version: input.version + 1,
        history: [{ ...fixtures["review-resolved"].value.history[0], reason: input.reason }],
      };
      return json(route, review);
    }
    return json(route, fixtures["error-not_found"].value);
  });
  await page.goto("/reviews");
  await page.getByLabel("Reviewer session token").fill("a".repeat(43));
  await page.getByRole("button", { name: "Connect reviewer session" }).click();
  await expect(page.getByRole("heading", { name: "Reviewer workspace" })).toBeVisible();
  await page.getByRole("link", { name: /Synthetic apartment/ }).first().click();
  await page.getByLabel("Next status").selectOption("resolved");
  await page.locator('select:has(option[value="dismissed"])').selectOption("dismissed");
  await page.getByLabel("Required reason").fill("Controlled browser integration test.");
  await page.getByRole("button", { name: "Save decision" }).click();
  await expect(page.getByText(/Decision saved/)).toBeVisible();
  await expect(page.getByText("Controlled browser integration test.")).toBeVisible();
  expect(decisions).toHaveLength(1);
  expect(decisions[0].version).toBe(1);
});
