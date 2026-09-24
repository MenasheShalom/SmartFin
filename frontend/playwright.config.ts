import { defineConfig, devices } from "@playwright/test";

// Runs against a live SmartFin with the demo data loaded (see README, "End-to-end tests").
export default defineConfig({
  testDir: "e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:8000",
    locale: "he-IL",
    timezoneId: "Asia/Jerusalem",
    trace: "retain-on-failure",
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM } : {},
  },
  projects: [
    { name: "phone", use: { ...devices["Pixel 7"], browserName: "chromium" }, testIgnore: /layout\.spec\.ts/ },
    {
      name: "phone-dark",
      use: { ...devices["Pixel 7"], browserName: "chromium", colorScheme: "dark" },
      testMatch: /app\.spec\.ts/,
      grep: /passes axe/,
    },
    { name: "desktop", use: { viewport: { width: 1280, height: 900 }, browserName: "chromium" }, testMatch: /layout\.spec\.ts/ },
  ],
});
