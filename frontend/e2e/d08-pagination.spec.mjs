import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";

const fixtures = JSON.parse(
  readFileSync(new URL("../../contracts/fixtures.json", import.meta.url), "utf8"),
);

test("Next and Previous return to rentals, not the map or page top", async ({ page }) => {
  const seenPages = [];

  await page.route("**/api/v1/**", (route) => {
    const url = new URL(route.request().url());
    let payload;

    if (url.pathname === "/api/v1/listings/map") payload = [];
    else if (url.pathname === "/api/v1/listings") {
      const pageNumber = Number(url.searchParams.get("page") || 1);
      seenPages.push(pageNumber);
      payload = {
        ...fixtures.listings.value,
        page: pageNumber,
        page_size: 20,
        total: 40,
        has_more: pageNumber === 1,
        items: Array.from({ length: 20 }, (_, index) => ({
          ...fixtures.listings.value.items[0],
          id: `00000000-0000-4000-8000-${String((pageNumber - 1) * 20 + index + 1).padStart(12, "0")}`,
          title: `Rental on page ${pageNumber} unit ${index + 1}`,
        })),
      };
    } else if (url.pathname === "/api/v1/exchange-rate") {
      payload = fixtures["exchange-rate"].value;
    } else if (url.pathname === "/api/v1/infrastructure") {
      payload = fixtures.infrastructure.value;
    } else {
      payload = fixtures["error-not_found"].value;
    }

    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(payload),
    });
  });

  await page.goto("/");
  await expect(page.getByText("Rental on page 1 unit 1")).toBeVisible();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(page).toHaveURL(/page=2/);
  await expect(page.getByText("Rental on page 2 unit 1")).toBeVisible();

  async function expectAtRentals() {
    await expect.poll(async () => page.evaluate(() => {
      const results = document.getElementById("rental-results");
      if (!results) return false;
      const top = results.getBoundingClientRect().top;
      return top >= 75 && top < 190 && window.scrollY > 200;
    })).toBe(true);
  }

  await expectAtRentals();
  await page.getByRole("button", { name: "Previous", exact: true }).click();
  await expect(page).toHaveURL(/page=1/);
  await expect(page.getByText("Rental on page 1 unit 1")).toBeVisible();
  await expectAtRentals();
  expect(seenPages).toContain(2);
  expect(seenPages).toContain(1);
});
