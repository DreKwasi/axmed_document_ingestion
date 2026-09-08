import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";

const sanovaFixture = fileURLToPath(
  new URL("../../backend/evals/fixtures/documents/sanova_offer_export_2026-08-03.json", import.meta.url)
);

test("a reviewer corrects a source-grounded extracted offer", async ({ page }) => {
  await page.goto("/");
  await page.locator('input[type="file"]').setInputFiles(sanovaFixture);

  await expect(page.getByText("Pending human review", { exact: true })).toBeVisible();
  await expect(page.getByText("0.035", { exact: false })).toHaveCount(0);

  await page.getByText("Sanotri-TLD").click();
  await expect(page.getByText("EUR 0.04 / tablet", { exact: false })).toBeVisible();
  await page.getByLabel("Correction value for Sanotri-TLD").fill("4.00");
  await page.getByRole("button", { name: "Save correction" }).click();
  await expect(
    page.getByRole("complementary", { name: "Sanotri-TLD" }).getByText("EUR 4", { exact: true })
  ).toBeVisible();
  await expect(page.getByText("0.044444", { exact: false })).toHaveCount(0);

  await page.getByLabel("Close product details").click();
  await expect(page.getByText("Pending review after correction", { exact: true })).toBeVisible();
});

test("opening a processed image source starts one review request", async ({ page }, testInfo) => {
  const imageDocument = {
    id: "processed-image",
    filename: "processed-image.jpg",
    source_name: "Processed image quotation",
    source_system: "image",
    status: "pending_review",
    quotation: null,
    reviews: [],
    image_extraction_attempts: [{
      approach: "ocr_assisted",
      status: "completed",
      result: { supplier: { name: "Supplier" }, line_items: [] },
      product_count: 1,
      extraction_confidence: { score: 90, band: "High", factors: [] },
      mapping_confidence: { score: 100, band: "High", issue_count: 0 },
    }],
  };
  const reviewableDocument = {
    ...imageDocument,
    quotation: {
      supplier: { name: "Supplier" },
      commercial_terms: {},
      line_items: [{
        product: { trade_name: "Reviewable product", inn: [], strength: [] },
        packaging: {}, quantity: {},
        pricing: { quoted_price: {}, normalized_price: {}, price_tiers: [], adjustments: [] },
        supply: {}, regulatory: {}, evidence: [],
      }],
      revision: 1,
      system_decision: "pending_review",
      review_status: "pending_review",
      review_issues: [],
    },
  };
  let reviewRequests = 0;

  await page.route("**/api/v1/documents", (route) => route.fulfill({ json: [imageDocument] }));
  await page.route("**/api/v1/documents/processed-image/events?after_id=0", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/documents/processed-image/events/stream?after_id=0", (route) => route.fulfill({ status: 204 }));
  await page.route("**/api/v1/documents/processed-image/image-extractions/ocr_assisted/review", (route) => {
    reviewRequests += 1;
    return route.fulfill({ json: reviewableDocument });
  });

  await page.goto("/");
  await page.getByText("Processed image quotation — OCR-assisted", { exact: true }).click();

  await expect(page.getByText("Reviewable product", { exact: true })).toBeVisible();
  await expect.poll(() => reviewRequests).toBe(1);
  await page.screenshot({ path: testInfo.outputPath("source-detail.png"), fullPage: true });
});
