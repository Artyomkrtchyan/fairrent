import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  testMatch: "**/*.spec.mjs",
  timeout: 30000,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    ...devices["Desktop Chrome"],
    baseURL: "http://127.0.0.1:4173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 4173 --strictPort",
    cwd: "..",
    url: "http://127.0.0.1:4173/",
    reuseExistingServer: !process.env.CI,
    timeout: 120000,
    env: { VITE_API_MODE: "real", VITE_API_BASE_URL: "http://127.0.0.1:4173" },
  },
});
