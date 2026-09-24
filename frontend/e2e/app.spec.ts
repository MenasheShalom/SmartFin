import { expect, test } from "@playwright/test";

import { expectAccessible, expectNoHorizontalScroll, login } from "./helpers";

test.describe.configure({ mode: "serial" });

test("a wrong password is refused", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("סיסמה").fill("not-the-password");
  await page.getByRole("button", { name: "כניסה" }).click();
  await expect(page.getByRole("alert")).toHaveText("הסיסמה שגויה.");
});

test("every screen renders on a phone, fits the width and passes axe", async ({ page }) => {
  await login(page);
  const screens: [string, string][] = [
    ["/", "צפי לסוף החודש"],
    ["/weekly", "הוצאות משתנות"],
    ["/history", "היסטוריה"],
    ["/transactions", "תנועות"],
    ["/plan", "התוכנית של"],
    ["/settings", "הגדרות"],
    ["/settings/categories", "קטגוריות"],
    ["/settings/rules", "כללי סיווג"],
    ["/settings/accounts", "חשבונות וסנכרון"],
    ["/alerts", "התראות"],
  ];
  for (const [path, heading] of screens) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 }).first()).toContainText(heading);
    await page.waitForLoadState("networkidle");
    await expectNoHorizontalScroll(page);
    await expectAccessible(page);
  }
});

test("the tab bar moves between screens", async ({ page }) => {
  await login(page);
  const nav = page.getByRole("navigation", { name: "ניווט ראשי" });
  await nav.getByRole("link", { name: /היסטוריה/ }).click();
  await expect(page).toHaveURL(/\/history$/);
  await expect(nav.getByRole("link", { name: /היסטוריה/ })).toHaveAttribute("aria-current", "page");
  await nav.getByRole("link", { name: /תזרים/ }).click();
  await expect(page).toHaveURL(/\/$/);
});

test("categorizing from the queue learns a rule", async ({ page }) => {
  await login(page);
  await page.goto("/transactions");
  const tab = page.getByRole("tab", { name: /לסיווג/ });
  await expect(tab).toContainText("(");
  const before = Number((await tab.textContent())?.match(/\d+/)?.[0]);
  expect(before).toBeGreaterThan(0);

  const name = await page.locator(".txn-hero-name").textContent();
  await page.getByRole("button", { name: "קניות" }).click();
  await expect(page.getByRole("checkbox")).toBeChecked();
  await page.getByRole("button", { name: "שמירה והבאה" }).click();
  await expect(page.locator(".toast").filter({ hasText: "נשמר" })).toBeVisible();
  await expect(tab).toContainText(before - 1 === 0 ? "לסיווג" : `(${before - 1})`);

  await page.goto("/settings/rules");
  await expect(page.getByRole("button", { name: new RegExp(name!.trim()) })).toBeVisible();
});

test("skipping moves to the next transaction without saving", async ({ page }) => {
  await login(page);
  await page.goto("/transactions");
  const first = await page.locator(".txn-hero-name").textContent();
  await page.getByRole("button", { name: "דלג" }).click();
  await expect(page.locator(".txn-hero-name")).not.toHaveText(first!);
});

test("editing a transaction's category from the list", async ({ page }) => {
  await login(page);
  await page.goto("/transactions");
  await page.getByRole("tab", { name: "כל התנועות" }).click();
  await page.getByRole("searchbox").fill("NETFLIX");
  const row = page.locator("button.list-row").first();
  await expect(row).toContainText("NETFLIX");
  await row.click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "אחר" }).click();
  await dialog.getByRole("button", { name: "העברות בין חשבונות" }).click();
  await dialog.getByRole("button", { name: "שמירה" }).click();
  await expect(dialog).toBeHidden();
  await expect(row).toContainText("העברות בין חשבונות");

  // Hand it back to the rules
  await row.click();
  await page.getByRole("dialog").getByRole("button", { name: "החזרה לסיווג אוטומטי" }).click();
  await expect(row).toContainText("מנויים");
});

test("the savings goal changes the weekly budget", async ({ page }) => {
  await login(page);
  await page.goto("/plan");
  const result = page.locator(".hero");
  const before = await result.textContent();
  await page.getByRole("button", { name: "עריכת החיסכון החודשי" }).click();
  const input = page.getByRole("dialog").getByRole("textbox");
  await input.fill("2500");
  await page.getByRole("dialog").getByRole("button", { name: "שמירה" }).click();
  await expect(page.getByRole("dialog")).toBeHidden();
  await expect(page.getByText("−₪2,500")).toBeVisible();
  await expect(result).not.toHaveText(before!);

  // Put it back for the other tests
  await page.getByRole("button", { name: "עריכת החיסכון החודשי" }).click();
  await page.getByRole("dialog").getByRole("textbox").fill("1000");
  await page.getByRole("dialog").getByRole("button", { name: "שמירה" }).click();
  await expect(page.getByText("−₪1,000")).toBeVisible();
});

test("history moves back and forward and shows a month's details", async ({ page }) => {
  await login(page);
  await page.goto("/history");
  const range = page.locator(".month-switcher-label");
  const newest = await range.textContent();
  await expect(page.getByRole("button", { name: "חודשים מאוחרים יותר" })).toBeDisabled();

  await page.getByRole("button", { name: "חודשים קודמים" }).click();
  await expect(range).not.toHaveText(newest!);
  await page.getByRole("button", { name: "חודשים מאוחרים יותר" }).click();
  await expect(range).toHaveText(newest!);

  // Swipe right: older months
  const chart = page.locator(".chart").first();
  const box = (await chart.boundingBox())!;
  await page.mouse.move(box.x + 60, box.y + 100);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width - 20, box.y + 100, { steps: 5 });
  await page.mouse.up();
  await expect(range).not.toHaveText(newest!);

  // Keyboard: the arrows pick months
  const details = page.locator(".details-title");
  const selected = await details.textContent();
  await page.locator("[tabindex='0']").filter({ has: page.locator(".chart") }).focus();
  await page.keyboard.press("ArrowLeft");
  await expect(details).not.toHaveText(selected!);

  await page.getByRole("button", { name: "הצג כטבלה" }).click();
  await expect(page.getByRole("table")).toBeVisible();
  await expect(page.getByRole("row")).toHaveCount(7);
});

test("weeks open to show their spending", async ({ page }) => {
  await login(page);
  await page.goto("/weekly");
  const weeks = page.locator("button.week-toggle");
  await weeks.first().click();
  await expect(weeks.first()).toHaveAttribute("aria-expanded", "true");
  await expect(page.locator(".week .list-row").first()).toBeVisible();
});

test("categories can be added, marked fixed and deleted", async ({ page }) => {
  await login(page);
  await page.goto("/settings/categories");
  await page.getByRole("button", { name: "קטגוריה חדשה" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("שם").fill("חוג ילדים");
  await dialog.getByRole("checkbox", { name: /הוצאה קבועה/ }).check();
  await dialog.getByRole("button", { name: "שמירה" }).click();
  await expect(dialog).toBeHidden();
  const fixedSection = page.getByRole("region", { name: "הוצאות קבועות" });
  await fixedSection.getByRole("button", { name: "חוג ילדים" }).click();
  page.once("dialog", (d) => d.accept());
  await page.getByRole("dialog").getByRole("button", { name: "מחיקה" }).click();
  await expect(page.getByRole("button", { name: "חוג ילדים" })).toHaveCount(0);
});

test("a category in use cannot be deleted", async ({ page }) => {
  await login(page);
  await page.goto("/settings/categories");
  await page.getByRole("button", { name: "סופר ומכולת" }).click();
  page.once("dialog", (d) => d.accept());
  await page.getByRole("dialog").getByRole("button", { name: "מחיקה" }).click();
  await expect(page.locator(".toast").filter({ hasText: "אי אפשר למחוק" })).toBeVisible();
});

test("alerts can be marked as read", async ({ page }) => {
  await login(page);
  await page.goto("/alerts");
  const read = page.getByRole("button", { name: /סימון כנקרא/ }).first();
  if (await read.count()) {
    await read.click();
    await expect(read).toBeHidden();
  }
});

test("logging out returns to the login screen", async ({ page }) => {
  await login(page);
  await page.goto("/settings");
  await page.getByRole("button", { name: "התנתקות" }).click();
  await expect(page.getByLabel("סיסמה")).toBeVisible();
  await page.goto("/plan");
  await expect(page.getByLabel("סיסמה")).toBeVisible();
});
