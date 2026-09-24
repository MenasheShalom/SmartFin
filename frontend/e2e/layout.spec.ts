import { expect, test } from "@playwright/test";

import { expectNoHorizontalScroll, login } from "./helpers";

test("desktop keeps a centred column and shows a year of history", async ({ page }) => {
  await login(page);
  const width = await page.locator("main.screen").evaluate((el) => el.getBoundingClientRect().width);
  expect(width).toBeLessThanOrEqual(720);
  await page.goto("/history");
  await expect(page.locator(".chart").first().locator("text").filter({ hasText: /׳|מאי|יוני|יולי|מרץ/ })).toHaveCount(12);
  await expectNoHorizontalScroll(page);
});
