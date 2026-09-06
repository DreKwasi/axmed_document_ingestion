import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";

const sanovaFixture = fileURLToPath(
  new URL("../../backend/evals/fixtures/documents/sanova_offer_export_2026-08-03.json", import.meta.url)
);
const ubuntuFixture = fileURLToPath(
  new URL("../../sample_documents/ubuntu_health_price_list_Q3-2026.json", import.meta.url)
);

test("a reviewer uploads a batch of documents and tracks aggregate progress", async ({ page }) => {
  await page.goto("/");
  await page.locator('input[type="file"]').setInputFiles([sanovaFixture, ubuntuFixture]);

  await expect(page.getByText(/Batch: 2 sources/i)).toBeVisible();
  await expect(page.getByText("sanova_offer_export_2026-08-03.json")).toBeVisible();
  await expect(page.getByText("ubuntu_health_price_list_Q3-2026.json")).toBeVisible();
});
