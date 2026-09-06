import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App.vue";

const api = vi.hoisted(() => ({
  fetchEvaluations: vi.fn(),
  runEvaluation: vi.fn(),
  uploadDocument: vi.fn(),
  confirmMapping: vi.fn(),
  reviewDocument: vi.fn(),
  sourceDocumentUrl: vi.fn((documentId: string) => `/api/v1/documents/${documentId}/source`)
}));

vi.mock("@/api", () => ({
  ...api
}));

describe("App", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.fetchEvaluations.mockResolvedValue({
      cases: [
        {
          id: "sanova-schema-reuse-v1",
          title: "Sanova ERP schema learns once and reuses deterministically",
          rubric: [
            {
              id: "canonical_fidelity",
              label: "Canonical fidelity",
              success_criterion: "Critical quotation fields match ground truth."
            }
          ]
        }
      ],
      runs: []
    });
  });

  it("shows the SQLite-backed evaluation lab and persists a requested run through the API", async () => {
    api.runEvaluation.mockResolvedValue({ id: "run-1", status: "completed" });
    const wrapper = mount(App);
    await flushPromises();

    await wrapper.findAll("button").find((button) => button.text() === "Evaluation lab")?.trigger("click");
    await wrapper.get(".primary-action").trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("Evaluation lab");
    expect(wrapper.text()).toContain("No evaluation runs.");
    expect(api.runEvaluation).toHaveBeenCalledOnce();
    expect(api.fetchEvaluations).toHaveBeenCalledTimes(2);
  });

  it("shows the human mapping checkpoint for a newly observed schema and confirms it", async () => {
    api.uploadDocument.mockResolvedValue({
      id: "document-1",
      filename: "sanova.json",
      status: "needs_mapping_confirmation",
      source_system: "SanovaERP",
      schema_version: "2.4.1",
      semantic_mapping_calls: 1,
      mapping: { id: "mapping-1", trust_state: "proposed", times_seen: 1, times_confirmed: 0, human_verified: false },
      quotation: { line_items: [], supplier: {}, commercial_terms: {}, revision: 1, review_status: "unreviewed", review_issues: [] },
      reviews: []
    });
    api.confirmMapping.mockResolvedValue({
      id: "document-1",
      filename: "sanova.json",
      status: "needs_review",
      source_system: "SanovaERP",
      schema_version: "2.4.1",
      semantic_mapping_calls: 1,
      mapping: { id: "mapping-1", trust_state: "trusted", times_seen: 1, times_confirmed: 1, human_verified: true },
      quotation: { line_items: [], supplier: {}, commercial_terms: {}, revision: 2, review_status: "unreviewed", review_issues: [] },
      reviews: []
    });
    const wrapper = mount(App);
    await flushPromises();

    const input = wrapper.get('input[type="file"]');
    Object.defineProperty(input.element, "files", {
      value: [new File(["{}"], "sanova.json", { type: "application/json" })]
    });
    await input.trigger("change");
    await flushPromises();

    expect(wrapper.text()).toContain("sanova.json · new mapping");
    expect(wrapper.text()).toContain("Confidence");
    await wrapper.get(".notice .primary-action").trigger("click");
    await flushPromises();
    expect(api.confirmMapping).toHaveBeenCalledWith("document-1");
    expect(wrapper.text()).toContain("unreviewed · v2");
  });

  it("keeps a line correction with its quoted value in the output table", async () => {
    const document = {
      id: "document-2",
      filename: "offer.json",
      status: "needs_review",
      source_system: "SupplierERP",
      schema_version: "1",
      semantic_mapping_calls: 0,
      quotation: {
        line_items: [
          {
            source_key: "line-1",
            product: { trade_name: "Example", inn: ["Example INN"] },
            packaging: {},
            quantity: { minimum_order_quantity: "10", minimum_order_quantity_uom: "pack" },
            pricing: {
              currency: "EUR",
              quoted_price: { amount: "3.15", uom: "pack" },
              normalized_price: { amount: "0.035", uom: "tablet" }
            },
            supply: {},
            evidence: [
              {
                canonical_field: "pricing.pack_price",
                source_path: "commercials.price_per_pack",
                extraction_method: "deterministic_mapping",
                confidence: "0.99"
              }
            ]
          }
        ],
        supplier: {},
        commercial_terms: {},
        revision: 1,
        review_status: "unreviewed",
        review_issues: []
      },
      reviews: []
    };
    api.uploadDocument.mockResolvedValue(document);
    api.reviewDocument.mockResolvedValue(document);
    const wrapper = mount(App);
    await flushPromises();

    const file = wrapper.get('input[type="file"]');
    Object.defineProperty(file.element, "files", {
      value: [new File(["{}"], "offer.json", { type: "application/json" })]
    });
    await file.trigger("change");
    await flushPromises();
    expect(wrapper.get("tfoot").text()).toContain("Approve");
    expect(wrapper.get("tfoot").text()).toContain("Reject");
    await wrapper.get('input[aria-label="Correction value for Example"]').setValue("4.00");
    await wrapper.findAll("button").find((button) => button.text() === "Correct")?.trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("commercials.price_per_pack");
    expect(wrapper.text()).toContain("99%");
    expect(api.reviewDocument).toHaveBeenCalledWith(
      "document-2",
      "correct",
      expect.objectContaining({
        expected_revision: 1,
        patches: [{ path: "line_items.0.pricing.pack_price", value: "4.00" }]
      })
    );
  });

  it("keeps each selected source available when ingesting multiple documents", async () => {
    api.uploadDocument
      .mockResolvedValueOnce({
        id: "document-a",
        filename: "first.json",
        status: "needs_mapping_confirmation",
        semantic_mapping_calls: 1,
        quotation: null,
        reviews: []
      })
      .mockResolvedValueOnce({
        id: "document-b",
        filename: "second.json",
        status: "needs_mapping_confirmation",
        semantic_mapping_calls: 1,
        quotation: null,
        reviews: []
      });
    const wrapper = mount(App);
    await flushPromises();

    const file = wrapper.get('input[type="file"]');
    Object.defineProperty(file.element, "files", {
      value: [
        new File(["{}"], "first.json", { type: "application/json" }),
        new File(["{}"], "second.json", { type: "application/json" })
      ]
    });
    await file.trigger("change");
    await flushPromises();

    expect(api.uploadDocument).toHaveBeenCalledTimes(2);
    expect(wrapper.text()).toContain("first.json · new mapping");
    expect(wrapper.text()).toContain("second.json · new mapping");
  });
});
