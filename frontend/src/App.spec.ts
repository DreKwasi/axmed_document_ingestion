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
  fetchEvents: vi.fn(),
  fetchDocument: vi.fn()
}));

vi.mock("@/api", () => ({
  ...api
}));

describe("App", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.fetchDocuments.mockResolvedValue([]);
    api.fetchEvents.mockResolvedValue([]);
  });

  afterEach(() => vi.unstubAllGlobals());

  it("keeps one Home title and places the ingest action in the main page", async () => {
    const wrapper = mount(App);
    await flushPromises();

    expect(wrapper.findAll("h1").filter((heading) => heading.text() === "Home")).toHaveLength(1);
    expect(wrapper.text()).not.toContain("Your sources, at a glance.");
    expect(wrapper.text()).not.toContain("Evaluation Lab");
    expect(wrapper.text()).not.toContain("Review desk");
    expect(wrapper.text()).not.toContain("Supplier intelligence");
    expect(wrapper.find("nav").exists()).toBe(false);
    const ingestButton = wrapper.findAll("button").find((button) => button.text() === "Ingest source");
    expect(ingestButton?.classes()).toContain("bg-[#123b37]");
    expect(ingestButton?.classes()).toContain("text-white");
    expect(ingestButton?.element.closest("header")).toBeNull();
    expect(api.fetchDocuments).toHaveBeenCalledOnce();
  });

  it("lists sources at a high level and opens a product breakdown with quoted quantity", async () => {
    api.fetchDocuments.mockResolvedValue([{
      id: "document-quantity",
      filename: "andina.pdf",
      source_name: "Farmaceutica Andina S.A.S. · FA-COT-2026-118",
      status: "pending_review",
      source_system: "pdf",
      semantic_mapping_calls: 0,
      product_counts: { extracted: 1, failed: 0 },
      notes: ["Quantity extracted from the source table."],
      quotation: {
        quotation_reference: "FA-COT-2026-118",
        supplier: { name: "Farmaceutica Andina S.A.S." },
        commercial_terms: {},
        line_items: [{
          source_key: "01",
          product: { trade_name: "Dolostop 500", inn: ["Paracetamol"], strength: [], dosage_form: "tablet" },
          packaging: { primary_pack: "PVC/Alu blister", units_per_pack: 20, unit_label: "tablet", packs_per_shipper: 12 },
          quantity: { quoted_quantity: "6000000", quoted_quantity_uom: "tablet" },
          pricing: { currency: "USD", quoted_price: { amount: "0.0091", uom: "tablet" }, normalized_price: { amount: "0.0091", uom: "tablet", derived: true, calculation: "quoted_price.amount", validation_status: "passed" }, price_tiers: [{ min_quantity: "100", price: "0.008" }], adjustments: [{ type: "rebate", value: "5" }] },
          supply: { minimum_remaining_shelf_life_percent: "80" },
          regulatory: { who_prequalified: true, who_pq_reference: "PQ-1", registered_markets: ["KE"] },
          evidence: [{ canonical_field: "product.trade_name", extraction_method: "table_extraction", confidence: "1.00" }]
        }],
        revision: 1,
        review_status: "pending_review",
        review_issues: [],
        field_reviews: [{
          field_path: "line_items[0].product.trade_name",
          value: "Dolostop 500",
          review_status: "pending_review",
          confidence_band: "Medium",
          confidence_reason: "source evidence: strong; association: limited; independent validation: unavailable",
          confidence: "1.00",
          extraction_method: "table_extraction",
          source_path: "andina.pdf",
          source_location: "page 1",
        }]
      },
      reviews: []
    }]);
    const wrapper = mount(App);
    await flushPromises();

    expect(wrapper.text()).toContain("Farmaceutica Andina S.A.S.");
    expect(wrapper.text()).toContain("Source");
    expect(wrapper.text()).not.toContain("File source");
    expect(wrapper.text()).not.toContain("Source name");
    expect(wrapper.text()).toContain("Download file");
    expect(wrapper.text()).toContain("Products");
    expect(wrapper.text()).toContain("1 extracted");
    expect(wrapper.text()).toContain("Quantity extracted from the source table.");
    expect(wrapper.text()).not.toContain("OCR");
    expect(wrapper.findAll("thead")[0].text()).toContain("Source");
    expect(wrapper.findAll("thead")[0].text()).not.toContain("File source");
    expect(wrapper.findAll("thead")[0].text()).not.toContain("Source name");
    await wrapper.get("button.group").trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("Product breakdown");
    expect(wrapper.text()).toContain("6,000,000 tablet");
    expect(wrapper.text()).toContain("Quoted quantity");

    // Click product row to open product details drawer
    await wrapper.find("tbody tr").trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("12 packs / shipper");
    expect(wrapper.text()).toContain("WHO prequalified");
    expect(wrapper.text()).toContain("markets: KE");
    expect(wrapper.text()).toContain("1 price tiers");
    expect(wrapper.text()).toContain("1 adjustments");
    expect(wrapper.text()).toContain("Derived value · Validation passed");
    expect(wrapper.text()).toContain("Confidence summary");
    expect(wrapper.text()).toContain("The values were recovered from clear source material.");
    expect(wrapper.text()).toContain("some lack an exact row or cell reference");
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
      quotation: { line_items: [], supplier: {}, commercial_terms: {}, revision: 1, system_decision: "pending_review", review_status: "pending_review", review_issues: [] },
      reviews: []
    });
    api.confirmMapping.mockResolvedValue({
      id: "document-1",
      filename: "sanova.json",
      status: "pending_review",
      source_system: "SanovaERP",
      schema_version: "2.4.1",
      semantic_mapping_calls: 1,
      mapping: { id: "mapping-1", trust_state: "trusted", times_seen: 1, times_confirmed: 1, human_verified: true },
      quotation: { line_items: [], supplier: {}, commercial_terms: {}, revision: 2, system_decision: "pending_review", review_status: "pending_review", review_issues: [] },
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
    expect(wrapper.text()).toContain("Confidence pending");
    await wrapper.findAll("button").find((button) => button.text() === "Confirm mapping")?.trigger("click");
    await flushPromises();
    expect(api.confirmMapping).toHaveBeenCalledWith("document-1");
    expect(wrapper.text()).toContain("Review");
  });

  it("keeps a line correction with its quoted value in the output table", async () => {
    const document = {
      id: "document-2",
      filename: "offer.json",
      status: "pending_review",
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
        review_status: "pending_review",
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

    // Verify Review Source dialog
    const reviewBtn = wrapper.findAll("button").find((button) => button.text().includes("Review source"));
    await reviewBtn?.trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("Review Source Decision");
    expect(wrapper.text()).toContain("Approve source");

    // Close review dialog to interact with product details
    const closeDialogBtn = wrapper.findAll("button").find((button) => button.attributes("aria-label") === "Close dialog");
    await closeDialogBtn?.trigger("click");
    await flushPromises();

    // Click product row to open product details drawer
    await wrapper.find("tbody tr").trigger("click");
    await flushPromises();

    await wrapper.get('input[aria-label="Correction value for Example"]').setValue("4.00");
    await wrapper.findAll("button").find((button) => button.text() === "Save correction")?.trigger("click");
    await flushPromises();

    expect(wrapper.text()).not.toContain("Field Evidence & Provenance");
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
    expect(wrapper.text()).toContain("First");
    expect(wrapper.text()).toContain("Second");
    expect(wrapper.findAll("a").filter((link) => link.text() === "Download file")).toHaveLength(2);
  });

  it("displays isolated failures in batch upload cleanly", async () => {
    api.uploadBatch.mockResolvedValue({
      id: "batch-err",
      name: "Batch Err",
      created_at: "2026-09-06T15:00:00Z",
      updated_at: "2026-09-06T15:00:00Z",
      total_documents: 2,
      status_counts: { pending_review: 1, failed: 1 },
      is_completed: true,
      documents: [
        {
          id: "valid-doc",
          filename: "valid.json",
          status: "pending_review",
          semantic_mapping_calls: 0,
          quotation: {
            quotation_reference: "REF-1",
            supplier: { name: "Supplier A" },
            commercial_terms: {},
            line_items: [],
            revision: 1,
            review_status: "pending_review",
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
    expect(wrapper.text()).toContain("Corrupt");
    expect(wrapper.text()).toContain("Supplier A · REF-1");
  });

  it("offers every supported intake format through the single multi-file ingest control", async () => {
    const wrapper = mount(App);
    await flushPromises();

    expect(wrapper.get('input[type="file"]').attributes("accept")).toContain("application/pdf");
    expect(wrapper.get('input[type="file"]').attributes("accept")).toContain("image/png");
    expect(wrapper.get('input[type="file"]').attributes("accept")).toContain("image/jpeg");
  });

  it("refreshes a document after a persisted processing event", async () => {
    const handlers = new Map<string, (event?: MessageEvent<string>) => void>();
    class FakeEventSource {
      constructor() {}
      addEventListener(type: string, handler: (event?: MessageEvent<string>) => void) {
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
    api.fetchDocument.mockResolvedValue({ ...uploaded, status: "pending_review" });
    const wrapper = mount(App);
    await flushPromises();
    const file = wrapper.get('input[type="file"]');
    Object.defineProperty(file.element, "files", {
      value: [new File(["{}"], "events.json", { type: "application/json" })]
    });
    await file.trigger("change");
    await flushPromises();
    handlers.get("processing")?.({ data: JSON.stringify({ id: 1, document_id: "document-events", stage: "pdf_extraction_prepared", phase: "Preparing", message: "Preparing quotation pages.", metadata: {} }) } as MessageEvent<string>);
    await flushPromises();

    expect(api.eventStreamUrl).toHaveBeenCalledWith("document-events");
    expect(api.fetchEvents).toHaveBeenCalledWith("document-events");
    expect(api.fetchDocument).toHaveBeenCalledWith("document-events");
    expect(wrapper.text()).toContain("Preparing quotation pages.");
    // Does not render a multi-event list card
    expect(wrapper.text()).not.toContain("Extraction activity");

    // Second ongoing event: dynamically updates to single active state
    handlers.get("processing")?.({
      data: JSON.stringify({
        id: 2,
        document_id: "document-events",
        stage: "pdf_semantic_extraction_started",
        phase: "In progress",
        message: "Identifying supplier, products, quantities, and prices.",
        metadata: {}
      })
    } as MessageEvent<string>);
    await flushPromises();
    expect(wrapper.text()).toContain("Identifying supplier, products, quantities, and prices.");

    // Final event: completion dismisses the extraction status indicator completely
    handlers.get("processing")?.({
      data: JSON.stringify({
        id: 3,
        document_id: "document-events",
        stage: "pdf_extraction_completed",
        phase: "Complete",
        message: "Supplier PDF extraction completed.",
        metadata: {}
      })
    } as MessageEvent<string>);
    await flushPromises();
    expect(wrapper.text()).not.toContain("Identifying supplier, products, quantities, and prices.");
    expect(wrapper.text()).not.toContain("Extraction activity");
  });

  it("opens the review dialog and records an approval with an optional reviewer note", async () => {
    const document = {
      id: "document-approve",
      filename: "offer.json",
      status: "pending_review",
      quotation: {
        quotation_reference: "REF-99",
        supplier: { name: "MedSupply Co" },
        commercial_terms: { currency: "USD" },
        line_items: [
          {
            source_key: "item-1",
            product: { trade_name: "Amoxicillin 500", inn: ["Amoxicillin"], dosage_form: "capsule" },
            packaging: {},
            quantity: { quoted_quantity: "1000", quoted_quantity_uom: "capsule" },
            pricing: { quoted_price: { amount: "0.05", uom: "capsule" }, normalized_price: {} },
            supply: {},
            evidence: [{ canonical_field: "product.trade_name", confidence: "0.95", extraction_method: "semantic" }]
          }
        ],
        revision: 2,
        review_status: "pending_review",
        review_issues: []
      },
      reviews: []
    };
    api.fetchDocuments.mockResolvedValue([document]);
    api.reviewDocument.mockResolvedValue({
      ...document,
      status: "approved",
      quotation: { ...document.quotation, review_status: "approved", revision: 3 }
    });
    const wrapper = mount(App);
    await flushPromises();

    // Open the source
    await wrapper.get("button.group").trigger("click");
    await flushPromises();

    // Open review dialog
    const reviewBtn = wrapper.findAll("button").find((b) => b.text().includes("Review source"));
    expect(reviewBtn).toBeDefined();
    await reviewBtn?.trigger("click");
    await flushPromises();

    // Verify dialog content
    expect(wrapper.text()).toContain("Review Source Decision");
    expect(wrapper.text()).toContain("Every completed extraction requires a human decision.");

    // Enter an optional review note
    const noteTextarea = wrapper.get("textarea#review-note");
    await noteTextarea.setValue("Pricing confirmed against supplier catalog.");

    // Click Approve source
    const approveBtn = wrapper.findAll("button").find((b) => b.text() === "Approve source");
    expect(approveBtn).toBeDefined();
    await approveBtn?.trigger("click");
    await flushPromises();

    expect(api.reviewDocument).toHaveBeenCalledWith(
      "document-approve",
      "approve",
      expect.objectContaining({
        expected_revision: 2,
        note: "Pricing confirmed against supplier catalog."
      })
    );
  });

  it("displays confidence and identifies low-confidence extracted fields as review issues", async () => {
    const document = {
      id: "document-multi-line",
      filename: "quotation.pdf",
      status: "pending_review",
      source_name: "PharmaGlobal Ltd",
      quotation: {
        quotation_reference: "PG-2026",
        supplier: { name: "PharmaGlobal" },
        commercial_terms: { currency: "USD" },
        line_items: [
          {
            source_key: "line-1",
            product: { trade_name: "HighConfidenceItem", inn: ["Substance A"], dosage_form: "tablet" },
            packaging: { primary_pack: "blister", units_per_pack: 10 },
            quantity: { quoted_quantity: "5000", quoted_quantity_uom: "tablet" },
            pricing: { quoted_price: { amount: "1.20", uom: "tablet" }, normalized_price: {} },
            supply: { lead_time_days: 14 },
            evidence: [{ canonical_field: "product.trade_name", confidence: "0.98", extraction_method: "table" }]
          },
          {
            source_key: "line-2",
            product: { trade_name: "LowerConfidenceItem", inn: ["Substance B"], dosage_form: "vial" },
            packaging: { primary_pack: "vial", units_per_pack: 1 },
            quantity: { quoted_quantity: "200", quoted_quantity_uom: "vial" },
            pricing: { quoted_price: { amount: "15.00", uom: "vial" }, normalized_price: {} },
            supply: { lead_time_days: 30 },
            evidence: [{ canonical_field: "product.trade_name", confidence: "0.72", extraction_method: "ocr" }]
          }
        ],
        revision: 1,
        system_decision: "pending_review",
        review_status: "pending_review",
        review_issues: [],
        field_reviews: [
          {
            field_path: "line_items[1].product.inn",
            confidence_band: "Low",
            confidence_reason: "source evidence: weak; association: limited; independent validation: unavailable"
          }
        ]
      },
      confidence_summary: { High: 6, Medium: 4, Low: 2 },
      review_reasons: ["line_items[1].product.inn: source evidence: weak; association: limited; independent validation: unavailable"],
      reviews: []
    };
    api.fetchDocuments.mockResolvedValue([document]);
    const wrapper = mount(App);
    await flushPromises();

    expect(wrapper.text()).toContain("lowest field band");

    // Open the source
    await wrapper.get("button.group").trigger("click");
    await flushPromises();

    // Check product breakdown contains both products
    expect(wrapper.text()).toContain("HighConfidenceItem");
    expect(wrapper.text()).toContain("LowerConfidenceItem");
    expect(wrapper.text()).toContain("Confidence");
    expect(wrapper.text()).toContain("Review issues");
    expect(wrapper.text()).toContain("Product / INN: source evidence: weak");
    expect(wrapper.text()).toContain("Low");

    // Click first product row to open drawer
    const rows = wrapper.findAll("tbody tr");
    expect(rows.length).toBeGreaterThanOrEqual(2);
    await rows[0].trigger("click");
    await flushPromises();

    // Internal provenance does not appear in the routine product-review drawer.
    expect(wrapper.text()).not.toContain("Field Evidence & Provenance");
    expect(wrapper.text()).toContain("Substance A");

    // Click second product row
    await rows[1].trigger("click");
    await flushPromises();

    // Verify drawer now shows second line
    expect(wrapper.text()).toContain("Substance B");
    expect(wrapper.text()).toContain("LowerConfidenceItem");
  });
});
