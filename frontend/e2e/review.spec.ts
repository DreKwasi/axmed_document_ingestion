import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";

const sanovaFixture = fileURLToPath(
  new URL("../../backend/evals/fixtures/documents/sanova_offer_export_2026-08-03.json", import.meta.url)
);

test("a reviewer confirms, corrects, and approves an extracted offer", async ({ page }) => {
  await page.goto("/");
  await page.locator('input[type="file"]').setInputFiles(sanovaFixture);
  await expect(page.getByText(/new source structure detected/i)).toBeVisible();

  await page.getByRole("button", { name: "Confirm mapping" }).click();
  await expect(page.getByText("Review", { exact: true })).toBeVisible();
  await expect(page.getByText("0.035", { exact: false })).toBeVisible();

  await page.getByLabel("Correction value for Sanotri-TLD").fill("4.00");
  await page.getByRole("button", { name: "Save correction" }).click();
  await expect(page.getByText("0.044444", { exact: false })).toBeVisible();

  await page.getByRole("button", { name: "Approve source" }).click();
  await expect(page.getByText("Ready", { exact: true })).toBeVisible();
});
