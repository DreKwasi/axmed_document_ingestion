import { describe, expect, it } from "vitest";

import { documentsToCsv } from "./exportCsv";
import type { DocumentResponse } from "@/types";

describe("documentsToCsv", () => {
  it("exports one flat row per product and retains source-level context", () => {
    const csv = documentsToCsv([{
      id: "source-1",
      filename: "offer.pdf",
      status: "pending_review",
      source_system: "pdf",
      extraction_confidence: { score: 100, band: "High", factors: [] },
      mapping_confidence: { score: 82, band: "Medium", issue_count: 1 },
      mapping_issues: [{ field_path: "line_items[0].pricing.pack_price", section: "pricing", code: "uncertain_mapping", message: "Confirm pack price", severity: "warning" }],
      quotation: {
        quotation_reference: "REF-1",
        supplier: { name: "Supplier" },
        commercial_terms: { currency: "USD" },
        line_items: [{
          product: { trade_name: "Medicine", inn: ["Ingredient A", "Ingredient B"], strength: [], dosage_form: "tablet" },
          packaging: {}, quantity: {},
          pricing: { currency: "USD", quoted_price: { amount: "1.25", uom: "tablet" }, normalized_price: {} },
          supply: {}, regulatory: {}, evidence: [],
        }],
        revision: 1, system_decision: "pending_review", review_status: "pending_review", review_issues: [],
      },
      extracted_source_facts: [{
        label: "Unmapped note", value: { text: "Supplier note" }, source_path: "$.notes[0]", extraction_method: "direct_json",
        confidence: "1.00", normalization_status: "unmapped", review_status: "not_reviewable",
      }],
      reviews: [],
    } as DocumentResponse]);

    const [header, sourceRow, productRow, factRow] = csv.split("\r\n");
    expect(header).toContain('"product"');
    expect(sourceRow).toContain('"source"');
    expect(productRow).toContain('"product"');
    expect(productRow).toContain('"offer.pdf"');
    expect(productRow).toContain('"Medicine"');
    expect(productRow).toContain('"Ingredient A; Ingredient B"');
    expect(factRow).toContain('"source_fact"');
    expect(factRow).toContain('"Unmapped note"');
  });
});
