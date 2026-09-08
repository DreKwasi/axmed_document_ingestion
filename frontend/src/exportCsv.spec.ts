import { describe, expect, it } from "vitest";

import { documentsToCsv } from "./exportCsv";
import type { DocumentResponse } from "@/types";

function parseCsv(csv: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let value = "";
  let quoted = false;

  for (let index = 0; index < csv.length; index += 1) {
    const character = csv[index];
    if (character === '"' && quoted && csv[index + 1] === '"') {
      value += '"';
      index += 1;
    } else if (character === '"') {
      quoted = !quoted;
    } else if (character === "," && !quoted) {
      row.push(value);
      value = "";
    } else if (character === "\r" && csv[index + 1] === "\n" && !quoted) {
      row.push(value);
      rows.push(row);
      row = [];
      value = "";
      index += 1;
    } else {
      value += character;
    }
  }
  row.push(value);
  rows.push(row);
  return rows;
}

describe("documentsToCsv", () => {
  it("exports terminal sources as user-facing product rows", () => {
    const completed = {
      id: "source-1", filename: "offer.pdf", status: "pending_review", source_system: "pdf",
      notes: ["Native text recovered cleanly."],
      extraction_confidence: {
        score: 74, band: "Medium",
        factors: [{ key: "legibility", label: "Text legibility", weight: 45, score: 60, reason: "Some text regions were unclear." }],
      },
      mapping_confidence: { score: 82, band: "Medium", issue_count: 2 },
      mapping_issues: [
        { field_path: "line_items[0].pricing.pack_price", section: "pricing", code: "uncertain_mapping", message: "Confirm pack price", severity: "warning" },
        { field_path: "line_items[0].pricing.quoted_price", section: "pricing", code: "uncertain_mapping", message: "Confirm quoted price", severity: "warning" },
      ],
      quotation: {
        quotation_reference: "REF-1", supplier: { name: "Supplier" }, commercial_terms: { currency: "USD" },
        line_items: [{
          product: { trade_name: "Medicine", inn: ["Ingredient A", "Ingredient B"], strength: [], dosage_form: "tablet" },
          packaging: { description: "10 x 10 tablets", presentation: "carton", primary_pack: "blister", units_per_pack: 100 },
          quantity: { quantity_basis: "forecast", quoted_quantity: "500" },
          pricing: { currency: "USD", quoted_price: { amount: "1.25", uom: "tablet" }, normalized_price: {} },
          supply: {}, regulatory: {}, evidence: [],
        }],
        revision: 1, system_decision: "pending_review", review_status: "pending_review", review_issues: [],
      },
      extracted_source_facts: [{
        label: "Internal fact", value: "value", source_path: "$.fact", extraction_method: "direct_json",
        confidence: "1.00", normalization_status: "unmapped", review_status: "not_reviewable",
      }],
      reviews: [
        { action: "corrected", prior_revision: 1, resulting_revision: 2, note: "Verified against source", patches: [] },
        { action: "approved", prior_revision: 2, resulting_revision: 3, patches: [] },
      ],
    } as DocumentResponse;
    const processing = {
      id: "source-2", filename: "processing.pdf", status: "processing", quotation: null, reviews: [],
    } as DocumentResponse;

    const csv = documentsToCsv([completed, processing]);
    const [headers, row] = parseCsv(csv);
    const values = Object.fromEntries(headers.map((header, index) => [header, row[index]]));

    expect(headers).not.toEqual(expect.arrayContaining([
      "record_type", "source_id", "source_status", "source_system", "quantity_basis", "currency",
      "presentation", "primary_pack", "fact_label", "fact_value",
    ]));
    expect(headers.filter((header) => header.includes("currency"))).toEqual(["commercial_currency"]);
    expect(values).toMatchObject({
      source_file: "offer.pdf", file_format: "PDF", failure_reason: "",
      source_notes: "Native text recovered cleanly.", extraction_confidence: "74",
      extraction_confidence_explanation: "Native text recovered cleanly. | Text legibility: Some text regions were unclear.",
      mapping_confidence: "82", mapping_issue_count: "2", active_ingredients: "Ingredient A; Ingredient B",
      commercial_currency: "USD", packaging_description: "10 x 10 tablets",
      issue_field_path: "line_items[0].pricing.pack_price; line_items[0].pricing.quoted_price",
      issue_section: "pricing; pricing", issue_message: "Confirm pack price; Confirm quoted price",
      issue_severity: "warning; warning", review_action: "corrected; approved",
      review_prior_revision: "1; 2", review_resulting_revision: "2; 3",
      review_note: "Verified against source; ",
    });
    expect(parseCsv(csv)).toHaveLength(2);
  });

  it("retains a summary row and failure reason for a terminal failed source", () => {
    const failed = {
      id: "source-failed", filename: "glare.jpg", status: "failed", source_system: "image",
      failure_reason: "The source was too unclear to extract reliably.", quotation: null, reviews: [],
    } as DocumentResponse;

    const [headers, row] = parseCsv(documentsToCsv([failed]));
    const values = Object.fromEntries(headers.map((header, index) => [header, row[index]]));

    expect(values.source_file).toBe("glare.jpg");
    expect(values.file_format).toBe("JPG");
    expect(values.failure_reason).toBe("The source was too unclear to extract reliably.");
    expect(values.product).toBe("");
  });
});
