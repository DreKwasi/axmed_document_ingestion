import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App.vue";

const api = vi.hoisted(() => ({
  fetchEvaluations: vi.fn(),
  runEvaluation: vi.fn(),
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

  afterEach(() => vi.unstubAllGlobals());

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

  it("shows persisted evaluation failures when a reviewer opens a run", async () => {
    api.fetchEvaluations.mockResolvedValue({
      cases: [],
      runs: [
        {
          id: "run-12345678",
          status: "completed",
          execution_mode: "recorded",
          created_at: "2026-09-06T15:00:00Z",
          summary: { case_count: 1, passed: 0, rubrics: [] },
          results: [
            {
              case_id: "email-correction-v1",
              status: "failed",
              scores: { canonical_fidelity: 0 },
              errors: ["Corrected price did not win."]
            }
          ]
        }
      ]
    });
    const wrapper = mount(App);
    await flushPromises();

    await wrapper.findAll("button").find((button) => button.text() === "Evaluation lab")?.trigger("click");
    await wrapper.get("summary").trigger("click");

    expect(wrapper.text()).toContain("email-correction-v1");
    expect(wrapper.text()).toContain("Corrected price did not win.");
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
    expect(wrapper.text()).toContain("Batch: 2 files");
    expect(wrapper.text()).toContain("first.json · new mapping");
    expect(wrapper.text()).toContain("second.json · new mapping");
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

    expect(wrapper.text()).toContain("Batch: 2 files (1 ready for review, 1 failed)");
    expect(wrapper.text()).toContain("corrupt.json · The uploaded JSON is invalid.");
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
