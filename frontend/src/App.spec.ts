import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App.vue";

const api = vi.hoisted(() => ({
  fetchDocuments: vi.fn(),
  uploadDocument: vi.fn(),
  uploadBatch: vi.fn(),
  fetchBatch: vi.fn(),
  confirmMapping: vi.fn(),
  reviewDocument: vi.fn(),
  sourceDocumentUrl: vi.fn((documentId: string) => `/api/v1/documents/${documentId}/source`),
  eventStreamUrl: vi.fn((documentId: string) => `/api/v1/documents/${documentId}/events/stream`),
  fetchDocument: vi.fn()
}));

vi.mock("@/api", () => ({
  ...api
}));

describe("App", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.fetchDocuments.mockResolvedValue([]);
  });

  afterEach(() => vi.unstubAllGlobals());

  it("opens on Home and removes the Evaluation Lab navigation", async () => {
    const wrapper = mount(App);
    await flushPromises();

    expect(wrapper.text()).toContain("Your sources, at a glance.");
    expect(wrapper.text()).not.toContain("Evaluation Lab");
    expect(wrapper.find("nav").exists()).toBe(false);
    expect(api.fetchDocuments).toHaveBeenCalledOnce();
  });

  it("lists sources at a high level and opens a product breakdown with quoted quantity", async () => {
    api.fetchDocuments.mockResolvedValue([{
      id: "document-quantity",
      filename: "andina.pdf",
      status: "needs_review",
      source_system: "pdf",
      semantic_mapping_calls: 0,
      quotation: {
        quotation_reference: "FA-COT-2026-118",
        supplier: { name: "Farmaceutica Andina S.A.S." },
        commercial_terms: {},
        line_items: [{
          source_key: "01",
          product: { trade_name: "Dolostop 500", inn: ["Paracetamol"], strength: [], dosage_form: "tablet" },
          packaging: { primary_pack: "PVC/Alu blister", units_per_pack: 20, unit_label: "tablet", packs_per_shipper: 12 },
          quantity: { quoted_quantity: "6000000", quoted_quantity_uom: "tablet" },
          pricing: { currency: "USD", quoted_price: { amount: "0.0091", uom: "tablet" }, normalized_price: {}, price_tiers: [{ min_quantity: "100", price: "0.008" }], adjustments: [{ type: "rebate", value: "5" }] },
          supply: { minimum_remaining_shelf_life_percent: "80" },
          regulatory: { who_prequalified: true, who_pq_reference: "PQ-1", registered_markets: ["KE"] },
          evidence: [{ canonical_field: "product.trade_name", extraction_method: "table_extraction", confidence: "1.00" }]
        }],
        revision: 1,
        review_status: "unreviewed",
        review_issues: []
      },
      reviews: []
    }]);
    const wrapper = mount(App);
    await flushPromises();

    expect(wrapper.text()).toContain("Farmaceutica Andina S.A.S.");
    expect(wrapper.text()).not.toContain("SourceConfidenceIssues");
    await wrapper.get("button.group").trigger("click");

    expect(wrapper.text()).toContain("Product breakdown");
    expect(wrapper.text()).toContain("6,000,000 tablet");
    expect(wrapper.text()).toContain("Quoted quantity");
    expect(wrapper.text()).toContain("12 packs / shipper");
    expect(wrapper.text()).toContain("WHO prequalified");
    expect(wrapper.text()).toContain("markets: KE");
    expect(wrapper.text()).toContain("1 price tiers");
    expect(wrapper.text()).toContain("1 adjustments");
    expect(wrapper.find("th").text()).not.toContain("Source");
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

    expect(wrapper.text()).toContain("New source structure detected");
    expect(wrapper.text()).toContain("Confidence");
    await wrapper.findAll("button").find((button) => button.text() === "Confirm mapping")?.trigger("click");
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
            product: { trade_name: "Example", inn: ["Example INN"], dosage_form: "tablet" },
            packaging: { presentation: "film-coated" },
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
    expect(wrapper.text()).toContain("Source decision");
    expect(wrapper.text()).toContain("Approve source");
    await wrapper.get('input[aria-label="Correction value for Example"]').setValue("4.00");
    await wrapper.findAll("button").find((button) => button.text() === "Save correction")?.trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("99%");
    expect(wrapper.text()).toContain("tablet · film-coated");
    expect(api.reviewDocument).toHaveBeenCalledWith(
      "document-2",
      "correct",
      expect.objectContaining({
        expected_revision: 1,
        patches: [{ path: "line_items.0.pricing.pack_price", value: "4.00" }]
      })
    );
  });

  it("retains every selected file when multiple files are chosen together as a batch", async () => {
    api.uploadBatch.mockResolvedValue({
      id: "batch-1",
      name: "Batch 1",
      created_at: "2026-09-06T15:00:00Z",
      updated_at: "2026-09-06T15:00:00Z",
      total_documents: 2,
      status_counts: { needs_mapping_confirmation: 2 },
      is_completed: false,
      documents: [
        {
          id: "first",
          filename: "first.json",
          status: "needs_mapping_confirmation",
          semantic_mapping_calls: 1,
          quotation: null,
          reviews: []
        },
        {
          id: "second",
          filename: "second.json",
          status: "needs_mapping_confirmation",
          semantic_mapping_calls: 1,
          quotation: null,
          reviews: []
        }
      ]
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

    expect(api.uploadBatch).toHaveBeenCalledOnce();
    expect(wrapper.text()).toContain("Batch: 2 sources");
    expect(wrapper.text()).toContain("first.json");
    expect(wrapper.text()).toContain("second.json");
  });

  it("displays isolated failures in batch upload cleanly", async () => {
    api.uploadBatch.mockResolvedValue({
      id: "batch-err",
      name: "Batch Err",
      created_at: "2026-09-06T15:00:00Z",
      updated_at: "2026-09-06T15:00:00Z",
      total_documents: 2,
      status_counts: { needs_review: 1, failed: 1 },
      is_completed: true,
      documents: [
        {
          id: "valid-doc",
          filename: "valid.json",
          status: "needs_review",
          semantic_mapping_calls: 0,
          quotation: {
            quotation_reference: "REF-1",
            supplier: { name: "Supplier A" },
            commercial_terms: {},
            line_items: [],
            revision: 1,
            review_status: "unreviewed",
            review_issues: []
          },
          reviews: []
        },
        {
          id: "bad-doc",
          filename: "corrupt.json",
          status: "failed",
          failure_reason: "The uploaded JSON is invalid.",
          semantic_mapping_calls: 0,
          quotation: null,
          reviews: []
        }
      ]
    });
    const wrapper = mount(App);
    await flushPromises();

    const file = wrapper.get('input[type="file"]');
    Object.defineProperty(file.element, "files", {
      value: [
        new File(["{}"], "valid.json", { type: "application/json" }),
        new File(["broken"], "corrupt.json", { type: "application/json" })
      ]
    });
    await file.trigger("change");
    await flushPromises();

    expect(wrapper.text()).toContain("Batch: 2 sources");
    expect(wrapper.text()).toContain("corrupt.json");
    expect(wrapper.text()).toContain("valid.json");
  });

  it("offers every supported intake format through the single multi-file ingest control", async () => {
    const wrapper = mount(App);
    await flushPromises();

    expect(wrapper.get('input[type="file"]').attributes("accept")).toContain("application/pdf");
    expect(wrapper.get('input[type="file"]').attributes("accept")).toContain("image/png");
    expect(wrapper.get('input[type="file"]').attributes("accept")).toContain("image/jpeg");
  });

  it("refreshes a document after a persisted processing event", async () => {
    const handlers = new Map<string, () => void>();
    class FakeEventSource {
      constructor() {}
      addEventListener(type: string, handler: () => void) {
        handlers.set(type, handler);
      }
      close() {}
    }
    vi.stubGlobal("EventSource", FakeEventSource);
    const uploaded = {
      id: "document-events",
      filename: "events.json",
      status: "needs_mapping_confirmation",
      semantic_mapping_calls: 1,
      quotation: null,
      reviews: []
    };
    api.uploadDocument.mockResolvedValue(uploaded);
    api.fetchDocument.mockResolvedValue({ ...uploaded, status: "needs_review" });
    const wrapper = mount(App);
    await flushPromises();
    const file = wrapper.get('input[type="file"]');
    Object.defineProperty(file.element, "files", {
      value: [new File(["{}"], "events.json", { type: "application/json" })]
    });
    await file.trigger("change");
    await flushPromises();
    handlers.get("processing")?.();
    await flushPromises();

    expect(api.eventStreamUrl).toHaveBeenCalledWith("document-events");
    expect(api.fetchDocument).toHaveBeenCalledWith("document-events");
  });
});
