import { expect, test } from "@playwright/test";

test("a reviewer runs and inspects a persisted evaluation", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Evaluation lab" }).click();
  await page.getByRole("button", { name: "Run" }).click();

  await expect(page.getByText("1/5 passed")).toBeVisible();
  await page.locator("summary").click();
  await expect(page.getByText("sanova-schema-reuse-v1")).toBeVisible();
  await expect(page.getByText("passed").last()).toBeVisible();
});
