import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";

const sanovaFixture = fileURLToPath(
  new URL("../../backend/evals/fixtures/documents/sanova_offer_export_2026-08-03.json", import.meta.url)
);
test("a reviewer uploads multiple documents through the same ingest action", async ({ page }) => {
  await page.goto("/");
  await page.locator('input[type="file"]').setInputFiles([sanovaFixture, sanovaFixture]);

  await expect(page.getByRole("table")).toBeVisible();
  await expect(page.getByText("Download file", { exact: false })).toHaveCount(2);
});
