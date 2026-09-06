import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";

const sanovaFixture = fileURLToPath(
  new URL("../../backend/evals/fixtures/documents/sanova_offer_export_2026-08-03.json", import.meta.url)
);

test("a reviewer confirms, corrects, and approves an extracted offer", async ({ page }) => {
  await page.goto("/");
  await page.locator('input[type="file"]').setInputFiles(sanovaFixture);
  await expect(page.getByText(/new mapping/i)).toBeVisible();

  await page.getByRole("button", { name: "Confirm map" }).click();
  await expect(page.getByText("unreviewed · v2")).toBeVisible();
  await expect(page.getByText("EUR 0.035 / tablet")).toBeVisible();

  await page.getByLabel("Correction value for Sanotri-TLD").fill("4.00");
  await page.getByRole("button", { name: "Correct" }).first().click();
  await expect(page.getByText("EUR 0.044444 / tablet")).toBeVisible();

  await page.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByText("approved · v4")).toBeVisible();
});
