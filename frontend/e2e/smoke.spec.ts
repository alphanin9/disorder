import { expect, test } from "@playwright/test";

test("starts a mock run from challenge detail", async ({ page }) => {
  await page.goto("/");

  const firstChallengeLink = page.locator("table tbody tr a").first();
  await expect(firstChallengeLink).toBeVisible({ timeout: 20_000 });
  await firstChallengeLink.click();

  await expect(page.getByRole("heading", { level: 3, name: "Start Run" })).toBeVisible();
  await page.getByRole("button", { name: "Start Run" }).click();

  await expect(page).toHaveURL(/\/runs\//, { timeout: 20_000 });

  const terminalBadge = page.locator("span").filter({ hasText: /^(deliverable_produced|flag_found|blocked|timeout)$/i }).first();
  await expect(terminalBadge).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("solve.py")).toBeVisible({ timeout: 60_000 });
});
