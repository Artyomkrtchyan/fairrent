import { test, expect } from "@playwright/test";

test("Browse page opens and exposes rental search controls", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Find your rental" })).toBeVisible();
  await expect(page.getByLabel("District", { exact: true })).toBeVisible();
});

test("Location form validates out-of-range coordinates", async ({ page }) => {
  await page.goto("/valuation");
  await page.getByLabel("Latitude").fill("999");
  await page.getByRole("button", { name: "Assess location" }).click();
  await expect(page.getByRole("alert")).toContainText("valid latitude");
});

test("Small screen exposes a usable filters toggle", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "Show filters" }).click();
  await expect(page.getByLabel("District", { exact: true })).toBeVisible();
});
