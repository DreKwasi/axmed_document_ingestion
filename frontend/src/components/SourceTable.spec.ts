import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import SourceTable from "./SourceTable.vue";

describe("SourceTable", () => {
  it("labels an empty, low-recovery image reading as material unusable", () => {
    const wrapper = mount(SourceTable, {
      props: {
        busy: false,
        documents: [{
          id: "glare-image",
          filename: "scan_03_glare_partial_andina_p1.jpg",
          source_name: "Scan 03 Glare Partial Andina P1",
          source_system: "image",
          status: "pending_review",
          quotation: null,
          reviews: [],
          image_extraction_attempts: [
            {
              approach: "ocr_assisted",
              status: "completed",
              result: { supplier: {}, line_items: [] },
              product_count: 0,
              extraction_confidence: { score: 46, band: "Low", factors: [] },
              mapping_confidence: { score: 91, band: "High", issue_count: 0 },
            },
            {
              approach: "vision_direct",
              status: "completed",
              result: { supplier: {}, line_items: [] },
              product_count: 0,
              extraction_confidence: { score: 46, band: "Low", factors: [] },
              mapping_confidence: { score: 82, band: "High", issue_count: 0 },
            },
          ],
        }],
      },
    });

    const rows = wrapper.findAll("tbody tr");
    expect(rows).toHaveLength(2);
    for (const row of rows) {
      expect(row.text()).toContain("Material unusable");
      expect(row.text()).not.toContain("Needs review");
    }
  });
});
