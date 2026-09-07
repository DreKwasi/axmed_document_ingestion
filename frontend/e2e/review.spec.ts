import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";

const sanovaFixture = fileURLToPath(
  new URL("../../backend/evals/fixtures/documents/sanova_offer_export_2026-08-03.json", import.meta.url)
);

test("a reviewer corrects a source-grounded extracted offer", async ({ page }) => {
  await page.goto("/");
  await page.locator('input[type="file"]').setInputFiles(sanovaFixture);

  await expect(page.getByText("Pending human review", { exact: true })).toBeVisible();
  await expect(page.getByText("0.035", { exact: false }).first()).toBeVisible();

  await page.getByText("Sanotri-TLD").click();
  await page.getByLabel("Correction value for Sanotri-TLD").fill("4.00");
  await page.getByRole("button", { name: "Save correction" }).click();
  await expect(page.getByText("0.044444", { exact: false }).first()).toBeVisible();

  await page.getByLabel("Close product details").click();
  await expect(page.getByText("Pending review after correction", { exact: true })).toBeVisible();
});
