import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App.vue";
import ProductDetailDrawer from "./components/ProductDetailDrawer.vue";
import SourceDetailHeader from "./components/SourceDetailHeader.vue";

const api = vi.hoisted(() => ({
  fetchDocuments: vi.fn(),
  deleteDocument: vi.fn(),
  uploadDocuments: vi.fn(),
  reextractDocument: vi.fn(),
  reviewDocument: vi.fn(),
  exportDocumentsUrl: vi.fn(() => "/api/v1/documents/export.csv"),
  sourceDocumentUrl: vi.fn((documentId: string) => `/api/v1/documents/${documentId}/source`),
  eventStreamUrl: vi.fn((documentId: string) => `/api/v1/documents/${documentId}/events/stream`),
  fetchEvents: vi.fn(),
  fetchDocument: vi.fn(),
  openImageExtractionForReview: vi.fn(),
}));

vi.mock("@/api", () => ({
  ...api
}));

describe("App", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.history.replaceState({}, "", "/");
    api.fetchDocuments.mockResolvedValue([]);
    api.fetchEvents.mockResolvedValue([]);
  });

  afterEach(() => vi.unstubAllGlobals());

  it("uses the source table as the Home surface with its actions in the table header", async () => {
    const wrapper = mount(App);
    await flushPromises();

    expect(wrapper.findAll("h1").filter((heading) => heading.text() === "Home")).toHaveLength(0);
    expect(wrapper.text()).not.toContain("Review uploaded supplier sources and open any source for its product breakdown.");
    expect(wrapper.text()).not.toContain("Your sources, at a glance.");
    expect(wrapper.text()).not.toContain("Evaluation Lab");
    expect(wrapper.text()).not.toContain("Review desk");
    expect(wrapper.text()).not.toContain("Supplier intelligence");
    expect(wrapper.find("nav").exists()).toBe(false);
    expect(wrapper.get('select[aria-label="Filter by status"]').classes()).toContain("app-select");
    const ingestButton = wrapper.findAll("button").find((button) => button.text() === "Ingest source");
    expect(ingestButton?.classes()).toContain("bg-[#261c7a]");
    expect(ingestButton?.classes()).toContain("text-white");
    expect(ingestButton?.element.closest("header")).toBeNull();
    expect(ingestButton?.element.closest(".rounded-2xl")).not.toBeNull();
    expect(api.fetchDocuments).toHaveBeenCalledOnce();
  });

  it("exports the loaded source and product data as a CSV", async () => {
    api.fetchDocuments.mockResolvedValue([{
      id: "export-source", filename: "offer.json", status: "pending_review", source_system: "json",
      quotation: { supplier: {}, commercial_terms: {}, line_items: [], revision: 1, system_decision: "pending_review", review_status: "pending_review", review_issues: [] },
      reviews: [],
    }]);
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);

    const wrapper = mount(App);
    await flushPromises();
    await wrapper.get("button").trigger("click");
    await flushPromises();

    expect(wrapper.findAll("button").find((button) => button.text() === "Export CSV")).toBeDefined();
    expect(api.exportDocumentsUrl).toHaveBeenCalledOnce();
    expect(click).toHaveBeenCalledOnce();
    const anchor = click.mock.contexts[0] as HTMLAnchorElement;
    expect(anchor.href).toContain("/api/v1/documents/export.csv");
    expect(anchor.download).toBe("axmed-export.csv");
  });

  it("explains a failed extraction instead of showing an unexplained needs-attention state", () => {
    const wrapper = mount(SourceDetailHeader, {
      props: {
        busy: false,
        document: {
          id: "failed-mapping",
          filename: "zenith.json",
          status: "failed",
          failure_reason: "No source-grounded quotation facts could be extracted from this JSON source.",
          quotation: null,
          reviews: [],
        },
      },
    });

    expect(wrapper.text()).toContain("Extraction failed");
    expect(wrapper.text()).toContain("No source-grounded quotation facts could be extracted from this JSON source.");
    expect(wrapper.text()).not.toContain("Needs attention");
  });

  it("preserves rejected as the source detail status", () => {
    const wrapper = mount(SourceDetailHeader, {
      props: {
        busy: false,
        document: {
          id: "rejected-source",
          filename: "andina.pdf",
          status: "rejected",
          quotation: {
            supplier: { name: "Farmaceutica Andina S.A.S." },
            commercial_terms: {},
            line_items: [],
            revision: 2,
            system_decision: "pending_review",
            review_status: "rejected",
            review_issues: [],
          },
          reviews: [{ action: "rejected", prior_revision: 1, resulting_revision: 2, rejection_reason: "incorrect_extraction", patches: [] }],
        },
      },
    });

    expect(wrapper.text()).toContain("Rejected");
    expect(wrapper.text()).not.toContain("Needs review");
  });

  it("displays page count in the metadata line and omits redundant source system card for PDFs", () => {
    const wrapper = mount(SourceDetailHeader, {
      props: {
        busy: false,
        document: {
          id: "doc-pdf",
          filename: "andina.pdf",
          status: "pending_review",
          source_system: "pdf",
          parsed_summary: { page_count: 2 },
          quotation: null,
          reviews: [],
        },
      },
    });

    expect(wrapper.text()).toContain("PDF");
    expect(wrapper.text()).not.toContain("andina.pdf");
    expect(wrapper.text()).toContain("2 pages");
    expect(wrapper.text()).not.toContain("Source Schema / System");
    expect(wrapper.text()).not.toContain("pdf · 2 pages");
  });

  it("displays external schema system and version in the metadata line for structured sources", () => {
    const wrapper = mount(SourceDetailHeader, {
      props: {
        busy: false,
        document: {
          id: "doc-erp",
          filename: "offer.json",
          status: "pending_review",
          source_system: "SupplierERP",
          schema_version: "1.0",
          quotation: null,
          reviews: [],
        },
      },
    });

    expect(wrapper.text()).toContain("JSON");
    expect(wrapper.text()).toContain("SupplierERP v1.0");
    expect(wrapper.text()).not.toContain("Source Schema / System");
  });

  it("displays shipping transit duration and payment terms in the delivery terms card", () => {
    const wrapper = mount(SourceDetailHeader, {
      props: {
        busy: false,
        document: {
          id: "doc-transit",
          filename: "andina.pdf",
          status: "pending_review",
          source_system: "pdf",
          quotation: {
            supplier: { name: "Farmaceutica Andina S.A.S.", country: "Colombia" },
            commercial_terms: {
              currency: "USD",
              incoterm: "FOB",
              incoterm_named_place: "Cartagena (COCTG)",
              transit_time_min_days: 26,
              transit_time_max_days: 32,
              payment_terms: "T/T 30 days from B/L date",
            },
            line_items: [],
            revision: 1,
            system_decision: "pending_review",
            review_status: "pending_review",
            review_issues: [],
          },
          reviews: [],
        },
      },
    });

    expect(wrapper.text()).toContain("Transit: 26–32 days");
    expect(wrapper.text()).toContain("Payment: T/T 30 days from B/L date");
  });

  it("displays shipping transit duration alongside lead time in ProductDetailDrawer", () => {
    const wrapper = mount(ProductDetailDrawer, {
      props: {
        isOpen: true,
        busy: false,
        lineIndex: 0,
        lineItem: {
          source_key: "01",
          product: { trade_name: "Amoxicillin 500mg", inn: ["Amoxicillin"], strength: [], dosage_form: "capsule" },
          packaging: {},
          quantity: {},
          pricing: {
            currency: null,
            quoted_price: { amount: "0.05", uom: "capsule" },
            pack_price: "0.899",
            normalized_price: { amount: "0.05", uom: "capsule" },
            price_tiers: [],
            adjustments: [],
          },
          supply: {
            lead_time_days: 42,
            shelf_life_months: 24,
            minimum_remaining_shelf_life_percent: "85",
            storage_conditions: "Below 25 C, dry",
          },
          regulatory: {},
          evidence: [],
        },
        document: {
          id: "doc-drawer-transit",
          filename: "offer.pdf",
          status: "pending_review",
          quotation: {
            supplier: { name: "MedSupply Ltd" },
            commercial_terms: {
              currency: "USD",
              transit_time_min_days: 26,
              transit_time_max_days: 32,
            },
            line_items: [],
            revision: 1,
            system_decision: "pending_review",
            review_status: "pending_review",
            review_issues: [],
          },
          reviews: [],
        },
      },
    });

    expect(wrapper.text()).toContain("Lead Time");
    expect(wrapper.text()).toContain("42 days");
    expect(wrapper.text()).toContain("Shipping Transit");
    expect(wrapper.text()).toContain("26–32 days");
    expect(wrapper.text()).toContain("Below 25 C, dry");
    expect(wrapper.text()).toContain("USD 0.899");
    expect(wrapper.text()).not.toContain("null 0.899");
  });

  it("distinguishes repeated mapping issue leaf fields by their canonical context", () => {
    const wrapper = mount(ProductDetailDrawer, {
      props: {
        isOpen: true,
        busy: false,
        lineIndex: 0,
        lineItem: {
          source_key: "01",
          product: {
            trade_name: "Combination treatment",
            inn: [],
            strength: [
              { value: "300", unit: "mg", per_value: "tablet" },
              { value: "150", unit: "mg", per_value: "tablet" },
            ],
          },
          packaging: {}, quantity: {}, pricing: {
            currency: "EUR", quoted_price: { amount: "3.15", uom: "tablet" },
            normalized_price: { amount: "3.15", uom: "tablet" }, price_tiers: [], adjustments: [],
          }, supply: {}, regulatory: {}, evidence: [],
        },
        document: {
          id: "doc-repeated-issues", filename: "offer.json", status: "pending_review", reviews: [],
          quotation: { supplier: {}, commercial_terms: {}, line_items: [], revision: 1, system_decision: "pending_review", review_status: "pending_review", review_issues: [] },
          mapping_issues: [
            "line_items[0].product.strength[0].unit",
            "line_items[0].product.strength[0].per_value",
            "line_items[0].product.strength[1].unit",
            "line_items[0].product.strength[1].per_value",
          ].map((field_path) => ({
            field_path, section: "product", code: "missing_mapping_evidence", severity: "warning",
            message: `Record source evidence for ${field_path.split(".").at(-1)}; no source-linked evidence was recorded for this field`,
          })),
        },
      },
    });

    expect(wrapper.text()).toContain("Strength 1 · Unit — no source-linked evidence was recorded for this field");
    expect(wrapper.text()).toContain("Strength 2 · Per Value — no source-linked evidence was recorded for this field");
  });

  it("formats strength mapping issues explicitly with ingredient name and potency", () => {
    const wrapper = mount(ProductDetailDrawer, {
      props: {
        isOpen: true,
        busy: false,
        lineIndex: 0,
        lineItem: {
          source_key: "01",
          product: {
            trade_name: "Sanotri-TLD",
            inn: ["Tenofovir disoproxil fumarate", "Lamivudine", "Dolutegravir"],
            strength: [
              { ingredient: "Tenofovir disoproxil fumarate", value: "300", unit: "mg", per_value: "1", per_unit: "tablet" },
              { ingredient: "Lamivudine", value: "300", unit: "mg", per_value: "1", per_unit: "tablet" },
              { ingredient: "Dolutegravir", value: "50", unit: "mg", per_value: "1", per_unit: "tablet" },
            ],
          },
          packaging: {}, quantity: {}, pricing: {
            currency: "EUR", quoted_price: { amount: "3.15", uom: "tablet" },
            normalized_price: { amount: "3.15", uom: "tablet" }, price_tiers: [], adjustments: [],
          }, supply: {}, regulatory: {}, evidence: [],
        },
        document: {
          id: "doc-tld-issues", filename: "offer.json", status: "pending_review", reviews: [],
          quotation: { supplier: {}, commercial_terms: {}, line_items: [], revision: 1, system_decision: "pending_review", review_status: "pending_review", review_issues: [] },
          mapping_issues: [
            {
              field_path: "line_items[0].product.strength[0]",
              section: "product",
              code: "missing_mapping_evidence",
              severity: "warning",
              message: "Record source evidence for Tenofovir disoproxil fumarate strength 300 mg / 1 tablet; no source-linked evidence was recorded for this field",
            },
          ],
        },
      },
    });

    expect(wrapper.text()).toContain("Tenofovir disoproxil fumarate strength 300 mg / 1 tablet — no source-linked evidence was recorded for this field");
    expect(wrapper.text()).toContain("Mapping issue");
  });

  it("anchors mapping issues directly to affected non-strength fields with explicit labels", () => {
    const wrapper = mount(ProductDetailDrawer, {
      props: {
        isOpen: true,
        busy: false,
        lineIndex: 0,
        lineItem: {
          product: {
            trade_name: "Sanotri-TLD",
            inn: ["Tenofovir", "Lamivudine"],
            strength: [],
            dosage_form: "tablet",
          },
          quantity: { quoted_quantity: "5000", quoted_quantity_uom: "packs" },
          packaging: {},
          pricing: {
            currency: "USD",
            quoted_price: { amount: "12.50", uom: "pack" },
            normalized_price: {},
            price_tiers: [],
            adjustments: [],
          },
          supply: { lead_time_days: 30 },
          regulatory: {},
          evidence: [],
        },
        document: {
          id: "doc-non-strength",
          filename: "quote.pdf",
          status: "pending_review",
          reviews: [],
          quotation: {
            supplier: {},
            commercial_terms: {},
            line_items: [],
            revision: 1,
            system_decision: "pending_review",
            review_status: "pending_review",
            review_issues: [],
          },
          mapping_issues: [
            {
              field_path: "line_items[0].product.trade_name",
              section: "product",
              code: "missing_mapping_evidence",
              severity: "warning",
              message: "Record source evidence for Trade name (Sanotri-TLD); no source-linked evidence was recorded for this field",
            },
            {
              field_path: "line_items[0].pricing.quoted_price.amount",
              section: "pricing",
              code: "missing_mapping_evidence",
              severity: "warning",
              message: "Record source evidence for Quoted price (USD 12.50 / pack); no source-linked evidence was recorded for this field",
            },
            {
              field_path: "line_items[0].supply.lead_time_days",
              section: "supply",
              code: "missing_mapping_evidence",
              severity: "warning",
              message: "Record source evidence for Lead time (30 days); no source-linked evidence was recorded for this field",
            },
          ],
        },
      },
    });

    expect(wrapper.text()).toContain("Trade name (Sanotri-TLD) — no source-linked evidence was recorded for this field");
    expect(wrapper.text()).toContain("Quoted price (USD 12.50 / pack) — no source-linked evidence was recorded for this field");
    expect(wrapper.text()).toContain("Lead time (30 days) — no source-linked evidence was recorded for this field");
    const issues = wrapper.findAll(".text-amber-700");
    expect(issues.length).toBeGreaterThanOrEqual(3);
  });

  it("lists sources at a high level and opens a product breakdown with quoted quantity", async () => {
    api.fetchDocuments.mockResolvedValue([{
      id: "document-quantity",
      filename: "andina.pdf",
      source_name: "Farmaceutica Andina S.A.S. · FA-COT-2026-118",
      status: "pending_review",
      source_system: "pdf",
      product_counts: { extracted: 1, failed: 0 },
      notes: ["Quantity extracted from the source table."],
      quotation: {
        quotation_reference: "FA-COT-2026-118",
        supplier: { name: "Farmaceutica Andina S.A.S." },
        commercial_terms: { hs_codes: ["3004.90", "3004.20"] },
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
          mapping_confidence_band: "Medium",
          mapping_confidence_score: 82,
          mapping_confidence_reason: "The value has source provenance but limited structural association.",
          source_evidence_score: "1.00",
          extraction_method: "table_extraction",
          source_path: "andina.pdf",
          source_location: "page 1",
        }]
      },
      extraction_confidence: { score: 100, band: "High", factors: [{ key: "format", label: "Source format", weight: 20, score: 100, reason: "The source format was accepted for extraction." }] },
      mapping_confidence: { score: 82, band: "Medium", issue_count: 0 },
      mapping_issues: [],
      reviews: []
    }]);
    const wrapper = mount(App);
    await flushPromises();

    expect(wrapper.text()).toContain("Farmaceutica Andina S.A.S.");
    expect(wrapper.text()).toContain("Source");
    expect(wrapper.text()).not.toContain("File source");
    expect(wrapper.text()).not.toContain("Source name");
    expect(wrapper.text()).toContain("andina.pdf");
    expect(wrapper.findAll("button").filter((button) => button.text() === "andina.pdf" && button.attributes("title") === "Preview andina.pdf")).toHaveLength(1);
    expect(wrapper.text()).toContain("Products");
    expect(wrapper.text()).toContain("1 extracted");
    expect(wrapper.text()).not.toContain("Quantity extracted from the source table.");
    expect(wrapper.text()).not.toContain("OCR");
    expect(wrapper.findAll("thead")[0].text()).toContain("Source");
    expect(wrapper.findAll("thead")[0].text()).not.toContain("File source");
    expect(wrapper.findAll("thead")[0].text()).not.toContain("Source name");
    await wrapper.get("button.group").trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("Product breakdown");
    expect(wrapper.text()).toContain("HS codes: 3004.90 · 3004.20");
    expect(wrapper.text()).toContain("6,000,000 tablet");
    expect(wrapper.text()).toContain("Quoted quantity");

    // Click product row to open product details drawer
    await wrapper.find("tbody tr").trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("12 packs / shipper");
    expect(wrapper.text()).toContain("Dosage Form");
    expect(wrapper.text()).not.toContain("Dosage Form / Route");
    expect(wrapper.text()).not.toContain("oral");
    expect(wrapper.text()).toContain("WHO prequalified");
    expect(wrapper.text()).toContain("markets: KE");
    expect(wrapper.text()).toContain("1 price tiers");
    expect(wrapper.text()).toContain("1 adjustments");
    expect(wrapper.text()).toContain("Derived value · Validation passed");
    expect(wrapper.text()).toContain("Extraction confidence");
    expect(wrapper.text()).toContain("Source content was recovered successfully");
    const extractionHelp = wrapper.get('button[aria-label="How extraction confidence is calculated"]');
    expect(wrapper.text()).not.toContain("How this is calculated");
    await extractionHelp.trigger("click");
    expect(wrapper.text()).toContain("How this is calculated");
    expect(extractionHelp.attributes("aria-expanded")).toBe("true");
    await extractionHelp.trigger("click");
    expect(extractionHelp.attributes("aria-expanded")).toBe("false");
    expect(wrapper.find("th").text()).not.toContain("Source");
  });

  it("shows OCR and vision image readings as separate source results", async () => {
    api.fetchDocuments.mockResolvedValue([{
      id: "image-source", filename: "glare.jpg", source_name: "Glare quotation", status: "pending_review",
      source_system: "image", reviews: [], quotation: null,
      image_extraction_attempts: [
        { approach: "ocr_assisted", status: "completed", result: { supplier: {}, line_items: [] }, product_count: 1,
          extraction_confidence: { score: 49, band: "Low", factors: [] }, mapping_confidence: { score: null, band: null, issue_count: 0 } },
        { approach: "vision_direct", status: "completed", result: { supplier: {}, line_items: [] }, product_count: 6,
          extraction_confidence: { score: 61, band: "Low", factors: [] }, mapping_confidence: { score: null, band: null, issue_count: 0 } },
      ],
    }]);

    const wrapper = mount(App);
    await flushPromises();

    const rows = wrapper.findAll("tbody tr");
    expect(rows).toHaveLength(2);
    expect(rows[0].text()).toContain("OCR-assisted");
    expect(rows[1].text()).toContain("Direct vision");
    expect(rows[0].findAll("td")[2].text()).toContain("—");
    expect(rows[0].findAll("td")[2].text()).not.toContain("No issues");
  });

  it("marks mapping confidence as not applicable when image extraction failed", async () => {
    api.fetchDocuments.mockResolvedValue([{
      id: "failed-image", filename: "glare.jpg", source_name: "Glare quotation", status: "failed",
      source_system: "image", reviews: [], quotation: null,
      image_extraction_attempts: [
        { approach: "ocr_assisted", status: "failed", result: null, product_count: 0, failure_reason: "No trustworthy text regions passed." },
        { approach: "vision_direct", status: "failed", result: null, product_count: 0, failure_reason: "No trustworthy text regions passed." },
      ],
    }]);

    const wrapper = mount(App);
    await flushPromises();

    const rows = wrapper.findAll("tbody tr");
    expect(rows).toHaveLength(2);
    for (const row of rows) {
      expect(row.findAll("td")[2].text()).toContain("Not applicable");
      expect(row.findAll("td")[2].text()).not.toContain("Pending");
    }
  });

  it("opens the selected image approach directly without a comparison interstitial", async () => {
    const baseDoc = {
      id: "image-source", filename: "glare.jpg", source_name: "Glare quotation", status: "pending_review",
      source_system: "image", reviews: [], quotation: null,
      image_extraction_attempts: [
        { approach: "ocr_assisted", status: "completed", result: { supplier: { name: "Andina" }, line_items: [{ product: { trade_name: "Dolostop 500", inn: [] }, pricing: { quoted_price: { amount: "1.00" } } }] }, product_count: 1,
          extraction_confidence: { score: 49, band: "Low", factors: [] }, mapping_confidence: { score: null, band: null, issue_count: 0 } },
        { approach: "vision_direct", status: "completed", result: { supplier: { name: "Andina" }, line_items: [{ product: { trade_name: "Direct Dolostop", inn: [] }, pricing: { quoted_price: { amount: "1.00" } } }] }, product_count: 1,
          extraction_confidence: { score: 61, band: "Low", factors: [] }, mapping_confidence: { score: null, band: null, issue_count: 0 } },
      ],
    };
    api.fetchDocuments.mockResolvedValue([baseDoc]);
    api.openImageExtractionForReview.mockResolvedValue({
      ...baseDoc,
      quotation: {
        supplier: { name: "Andina" },
        quotation_reference: "REF-1",
        commercial_terms: {},
        line_items: [{ product: { trade_name: "Dolostop 500", inn: [] }, pricing: { quoted_price: { amount: "1.00" } }, packaging: {}, quantity: {}, supply: {}, regulatory: {}, evidence: [] }],
        revision: 1,
        system_decision: "pending_review",
        review_status: "pending_review",
        review_issues: [],
      },
    });

    const wrapper = mount(App);
    await flushPromises();

    const rows = wrapper.findAll("tbody tr");
    await rows[0].trigger("click");
    await flushPromises();

    expect(api.openImageExtractionForReview).toHaveBeenCalledOnce();
    expect(api.openImageExtractionForReview).toHaveBeenCalledWith("image-source", "ocr_assisted");
    expect(wrapper.text()).not.toContain("Compare image extractions");
    expect(wrapper.text()).toContain("Dolostop 500");
  });

  it("stays on the Home page when an image is uploaded", async () => {
    api.fetchDocuments.mockResolvedValue([]);
    api.uploadDocuments.mockResolvedValue([{
      id: "new-image",
      filename: "photo.png",
      source_system: "image",
      status: "pending_review",
      reviews: [],
      quotation: null,
      image_extraction_attempts: [],
    }]);

    const wrapper = mount(App);
    await flushPromises();

    const input = wrapper.get('input[type="file"]');
    const file = new File(["dummy"], "photo.png", { type: "image/png" });
    Object.defineProperty(input.element, "files", { value: [file] });
    await input.trigger("change");
    await flushPromises();

    expect(wrapper.text()).toContain("Uploaded sources");
    expect(wrapper.text()).not.toContain("Back to sources");
  });

  it("allows switching between OCR-assisted and Direct vision readings in detail header", async () => {
    const baseDoc = {
      id: "image-source", filename: "glare.jpg", source_name: "Glare quotation", status: "pending_review",
      source_system: "image", reviews: [],
      quotation: {
        supplier: { name: "Andina" },
        quotation_reference: "REF-1",
        commercial_terms: {},
        line_items: [{ product: { trade_name: "Dolostop 500", inn: [] }, pricing: { quoted_price: { amount: "1.00" } }, packaging: {}, quantity: {}, supply: {}, regulatory: {}, evidence: [] }],
        revision: 1,
        system_decision: "pending_review",
        review_status: "pending_review",
        review_issues: [],
      },
      image_extraction_attempts: [
        { approach: "ocr_assisted", status: "completed", result: { supplier: { name: "Andina" }, line_items: [] }, product_count: 1,
          extraction_confidence: { score: 49, band: "Low", factors: [] }, mapping_confidence: { score: null, band: null, issue_count: 0 } },
        { approach: "vision_direct", status: "completed", result: { supplier: { name: "Andina" }, line_items: [] }, product_count: 2,
          extraction_confidence: { score: 61, band: "Low", factors: [] }, mapping_confidence: { score: null, band: null, issue_count: 0 } },
      ],
    };
    api.fetchDocuments.mockResolvedValue([baseDoc]);
    api.openImageExtractionForReview.mockResolvedValue({
      ...baseDoc,
      quotation: {
        ...baseDoc.quotation,
        line_items: [{ product: { trade_name: "Direct Dolostop", inn: [] }, pricing: { quoted_price: { amount: "2.00" } }, packaging: {}, quantity: {}, supply: {}, regulatory: {}, evidence: [] }],
      },
    });

    const wrapper = mount(App);
    await flushPromises();

    const rows = wrapper.findAll("tbody tr");
    await rows[0].trigger("click");
    await flushPromises();

    const visionButton = wrapper.findAll("button").find((b) => b.text() === "Direct vision");
    expect(visionButton).toBeDefined();
    await visionButton!.trigger("click");
    await flushPromises();

    expect(api.openImageExtractionForReview).toHaveBeenCalledWith("image-source", "vision_direct");
  });

  it("does not present a completed image review event as active extraction", async () => {
    api.fetchDocuments.mockResolvedValue([{
      id: "reviewed-image", filename: "image.jpg", status: "pending_review", source_system: "image",
      quotation: { supplier: {}, commercial_terms: {}, line_items: [], revision: 1, system_decision: "pending_review", review_status: "pending_review", review_issues: [] },
      reviews: [],
    }]);
    api.fetchEvents.mockResolvedValue([{
      id: 9, document_id: "reviewed-image", stage: "image_extraction_opened_for_review",
      phase: "In progress", message: "Image extraction result opened for human review.", metadata: {},
    }]);

    const wrapper = mount(App);
    await flushPromises();
    await wrapper.get("button.group").trigger("click");
    await flushPromises();

    expect(wrapper.text()).not.toContain("Image extraction result opened for human review.");
    expect(wrapper.text()).not.toContain("In progress:");
  });

  it("explains when extraction is waiting for service configuration", async () => {
    api.fetchDocuments.mockResolvedValue([{
      id: "awaiting-pdf", filename: "andina.pdf", status: "needs_semantic_extraction", source_system: "pdf",
      quotation: null, reviews: [],
    }]);
    api.fetchEvents.mockResolvedValue([{
      id: 10, document_id: "awaiting-pdf", stage: "pdf_extraction_awaiting_model_configuration",
      phase: "Waiting", message: "Waiting for the extraction service to be configured.", metadata: {},
    }]);

    const wrapper = mount(App);
    await flushPromises();
    await wrapper.get("button.group").trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("Waiting for configuration:");
    expect(wrapper.text()).toContain("Waiting for the extraction service to be configured.");
    expect(wrapper.text()).toContain("No extraction is running");
    expect(wrapper.text()).not.toContain("In progress:");
  });

  it("confirms and deletes an uploaded source from the table", async () => {
    api.fetchDocuments.mockResolvedValue([{
      id: "delete-me",
      filename: "delete-me.pdf",
      source_name: "Supplier quotation",
      status: "pending_review",
      quotation: null,
      reviews: [],
    }]);
    api.deleteDocument.mockResolvedValue(undefined);
    vi.stubGlobal("confirm", vi.fn(() => true));

    const wrapper = mount(App);
    await flushPromises();
    await wrapper.get('button[aria-label="Delete Supplier quotation"]').trigger("click");
    await flushPromises();

    expect(window.confirm).toHaveBeenCalledWith(
      "Delete Supplier quotation? This removes the uploaded file and all extracted data."
    );
    expect(api.deleteDocument).toHaveBeenCalledWith("delete-me");
    expect(wrapper.text()).toContain("No sources yet.");
  });

  it("offers explicit JSON re-extraction after a failed extraction", async () => {
    const wrapper = mount(SourceDetailHeader, {
      props: {
        busy: false,
        document: {
          id: "document-1",
          filename: "sanova.json",
          status: "failed",
          failure_reason: "No source-grounded quotation facts could be extracted from this JSON source.",
          quotation: null,
          reviews: []
        }
      }
    });

    await wrapper.get("button:nth-of-type(2)").trigger("click");
    expect(wrapper.emitted("reextract")).toHaveLength(1);
    expect(wrapper.text()).not.toContain("Confirm mapping");
  });

  it("keeps a line correction with its quoted value in the output table", async () => {
    const document = {
      id: "document-2",
      filename: "offer.json",
      status: "pending_review",
      source_system: "SupplierERP",
      schema_version: "1",
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
              normalized_price: { amount: "0.035714285714", uom: "tablet" }
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
    api.uploadDocuments.mockResolvedValue([document]);
    api.reviewDocument.mockResolvedValue(document);
    const wrapper = mount(App);
    await flushPromises();

    const file = wrapper.get('input[type="file"]');
    Object.defineProperty(file.element, "files", {
      value: [new File(["{}"], "offer.json", { type: "application/json" })]
    });
    await file.trigger("change");
    await flushPromises();

    expect(wrapper.find("table").text()).not.toContain("Normalized");

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

    expect(wrapper.text()).toContain("EUR 0.04 / tablet");
    expect(wrapper.text()).not.toContain("0.035714");
    const correctionOptions = wrapper.get('select[aria-label="Correction field"]').findAll("option").map((option) => option.text());
    expect(correctionOptions).toContain("Product identity · Active ingredients (INN)");
    expect(correctionOptions).toContain("Pricing · Price tiers");
    expect(correctionOptions).toContain("Quantity & packaging · MOQ");
    expect(correctionOptions).toContain("Supply · Cold chain required");
    expect(correctionOptions).toContain("Regulatory · Registered markets");

    await wrapper.get('input[aria-label="Correction value for Example"]').setValue("4.00");
    await wrapper.findAll("button").find((button) => button.text() === "Save correction")?.trigger("click");
    await flushPromises();

    expect(wrapper.text()).not.toContain("Field Evidence & Provenance");
    expect(wrapper.text()).toContain("Dosage form");
    expect(wrapper.text()).toContain("Dosage Formtablet");
    expect(wrapper.text()).not.toContain("tablet · film-coated");
    expect(api.reviewDocument).toHaveBeenCalledWith(
      "document-2",
      "correct",
      expect.objectContaining({
        expected_revision: 1,
        patches: [{ path: "line_items.0.pricing.pack_price", value: "4.00" }]
      })
    );
  });

  it("retains every selected file when multiple files are uploaded together", async () => {
    api.uploadDocuments.mockResolvedValue([
      {
        id: "first",
        filename: "first.json",
        status: "pending_extraction",
        quotation: null,
        reviews: []
      },
      {
        id: "second",
        filename: "second.json",
        status: "pending_extraction",
        quotation: null,
        reviews: []
      }
    ]);
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

    expect(api.uploadDocuments).toHaveBeenCalledOnce();
    expect(wrapper.text()).toContain("First");
    expect(wrapper.text()).toContain("Second");
    expect(wrapper.findAll("button").filter((button) => ["first.json", "second.json"].includes(button.text()))).toHaveLength(2);
  });

  it("previews JSON source files inside the platform from the Home filename", async () => {
    api.fetchDocuments.mockResolvedValue([{
      id: "preview-json",
      filename: "offer.json",
      source_name: "Preview supplier",
      status: "pending_review",
      mapping_confidence: { score: 100, band: "High", issue_count: 0 },
      quotation: null,
      reviews: [],
    }]);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      text: vi.fn().mockResolvedValue('{"supplier":"Preview supplier"}'),
    }));

    const wrapper = mount(App);
    await flushPromises();
    await wrapper.get('button[title="Preview offer.json"]').trigger("click");
    await flushPromises();

    const dialog = document.body.querySelector('[role="dialog"]');
    expect(dialog?.textContent).toContain("Source preview");
    expect(dialog?.textContent).toContain('"supplier": "Preview supplier"');
    expect(dialog?.getAttribute("aria-modal")).toBe("true");
    expect(api.sourceDocumentUrl).toHaveBeenCalledWith("preview-json");
  });

  it("uses backend-provided review states and flat status colors", async () => {
    api.fetchDocuments.mockResolvedValue([
      { id: "pre", filename: "pre.json", status: "pre_approved", mapping_confidence: { score: 100, band: "High", issue_count: 0 }, quotation: null, reviews: [] },
      { id: "review", filename: "review.pdf", status: "pending_review", mapping_confidence: { score: 82, band: "Medium", issue_count: 2 }, quotation: null, reviews: [] },
      { id: "approved", filename: "approved.eml", status: "approved", quotation: null, reviews: [] },
      { id: "failed", filename: "failed.jpg", status: "failed", quotation: null, reviews: [] },
    ]);

    const wrapper = mount(App);
    await flushPromises();

    expect(wrapper.text()).toContain("Pre-approved");
    expect(wrapper.text()).toContain("Needs review");
    expect(wrapper.text()).toContain("Approved");
    expect(wrapper.text()).toContain("Extraction failed");
    expect(wrapper.html()).not.toContain("gradient");
  });

  it("filters source results by their displayed status", async () => {
    api.fetchDocuments.mockResolvedValue([
      { id: "pre", filename: "pre.json", source_name: "Pre-approved supplier", status: "pre_approved", mapping_confidence: { score: 100, band: "High", issue_count: 0 }, quotation: null, reviews: [] },
      { id: "review", filename: "review.pdf", source_name: "Review supplier", status: "pending_review", mapping_confidence: { score: 82, band: "Medium", issue_count: 2 }, quotation: null, reviews: [] },
      { id: "approved", filename: "approved.eml", source_name: "Approved supplier", status: "approved", quotation: null, reviews: [] },
      { id: "failed", filename: "failed.jpg", source_name: "Failed supplier", status: "failed", quotation: null, reviews: [] },
    ]);
    const wrapper = mount(App);
    await flushPromises();

    await wrapper.get('select[aria-label="Filter by status"]').setValue("approved");

    expect(wrapper.text()).toContain("Approved supplier");
    expect(wrapper.text()).not.toContain("Review supplier");
    expect(wrapper.text()).toContain("1 of 5 extraction results");
  });

  it("persists an opened source in the URL and restores it after refresh", async () => {
    const document = {
      id: "persistent-source",
      filename: "persistent.json",
      source_name: "Persistent supplier",
      status: "pending_review",
      mapping_confidence: { score: 100, band: "High", issue_count: 0 },
      quotation: { supplier: {}, commercial_terms: {}, line_items: [], revision: 1, system_decision: "pending_review", review_status: "pending_review", review_issues: [] },
      reviews: [],
    };
    api.fetchDocuments.mockResolvedValue([document]);

    const firstMount = mount(App);
    await flushPromises();
    await firstMount.get("button.group").trigger("click");
    await flushPromises();

    expect(window.location.search).toBe("?source=persistent-source");
    expect(firstMount.text()).toContain("Back to sources");
    firstMount.unmount();

    const refreshedMount = mount(App);
    await flushPromises();

    expect(refreshedMount.text()).toContain("Back to sources");
    expect(refreshedMount.text()).toContain("Persistent supplier");
  });

  it("displays isolated failures from a multi-file upload cleanly", async () => {
    api.uploadDocuments.mockResolvedValue([
      {
        id: "valid-doc",
        filename: "valid.json",
        status: "pending_review",
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
        quotation: null,
        reviews: []
      }
    ]);
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
      status: "pending_extraction",
      quotation: null,
      reviews: []
    };
    api.uploadDocuments.mockResolvedValue([uploaded]);
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
    expect(wrapper.text()).toContain("Source Approved");
    expect(wrapper.text()).toContain("Quotation approved and marked ready for commercial export.");
    expect(wrapper.text()).toContain("Approved");
    expect(wrapper.text()).toContain("Uploaded sources");
    expect(wrapper.text()).not.toContain("Back to sources");
  });

  it("displays 'Rejected' status and triggers an info toast notification when human review is rejected", async () => {
    const document = {
      id: "document-reject",
      filename: "offer-reject.json",
      source_system: "SupplierERP",
      status: "pending_review",
      quotation: {
        supplier: { name: "Supplier Reject" },
        quotation_reference: "REJ-1",
        commercial_terms: {},
        line_items: [
          {
            product: { trade_name: "Amoxicillin 250mg", inn: ["Amoxicillin"] },
            pricing: { quoted_price: { amount: "0.05" } },
            quantity: { quoted_quantity: 100 },
          }
        ],
        revision: 1,
        review_status: "pending_review",
        review_issues: []
      },
      reviews: []
    };
    api.fetchDocuments.mockResolvedValue([document]);
    api.reviewDocument.mockResolvedValue({
      ...document,
      status: "rejected",
      quotation: { ...document.quotation, review_status: "rejected", revision: 2 }
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

    // Select a rejection reason
    const reasonSelect = wrapper.get("select#rejection-reason");
    expect(reasonSelect.classes()).toContain("app-select");
    await reasonSelect.setValue("unreadable_source");

    // Click Reject source
    const rejectBtn = wrapper.findAll("button").find((b) => b.text() === "Reject");
    expect(rejectBtn).toBeDefined();
    await rejectBtn?.trigger("click");
    await flushPromises();

    expect(api.reviewDocument).toHaveBeenCalledWith(
      "document-reject",
      "reject",
      expect.objectContaining({
        expected_revision: 1,
        rejection_reason: "unreadable_source",
      })
    );
    expect(wrapper.text()).toContain("Source Rejected");
    expect(wrapper.text()).toContain("Rejected");
    expect(wrapper.text()).toContain("Uploaded sources");
    expect(wrapper.text()).not.toContain("Back to sources");
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
        review_issues: [
          {
            field_path: "line_items[1].product.inn",
            code: "unverified_source",
            message: "Active ingredient requires confirmation",
            severity: "warning"
          }
        ],
        field_reviews: [
          {
            field_path: "line_items[1].product.inn",
            mapping_confidence_band: "Low",
            mapping_confidence_score: 42,
            mapping_confidence_reason: "The source-to-schema association conflicts with another value.",
            source_evidence_score: "0.72"
          }
        ]
      },
      extraction_confidence: { score: 61, band: "Low", factors: [] },
      mapping_confidence: { score: 74, band: "Medium", issue_count: 1 },
      mapping_issues: [{ field_path: "line_items[1].product.inn", section: "product", code: "uncertain_mapping", message: "Active ingredient requires confirmation", severity: "warning" }],
      reviews: []
    };
    api.fetchDocuments.mockResolvedValue([document]);
    const wrapper = mount(App);
    await flushPromises();

    expect(wrapper.text()).toContain("Extraction confidence");

    // Open the source
    await wrapper.get("button.group").trigger("click");
    await flushPromises();

    // Check product breakdown contains both products
    expect(wrapper.text()).toContain("HighConfidenceItem");
    expect(wrapper.text()).toContain("LowerConfidenceItem");
    expect(wrapper.text()).toContain("Mapping confidence");
    expect(wrapper.text()).not.toContain("Mapping issues");
    const mappingDefinitionHelp = wrapper.get('button[aria-label="How mapping confidence is calculated"]');
    await mappingDefinitionHelp.trigger("click");
    expect(wrapper.text()).toContain("How mapping confidence is built");
    expect(wrapper.text()).toContain("The product score is the average of those field scores.");
    expect(wrapper.text()).toContain("Low");
    expect(wrapper.findAll("tbody tr")[1].findAll("td")[4].text()).toContain("1 mapping issue");
    expect(wrapper.findAll("tbody tr")[1].findAll("td")[4].find("button").attributes("title")).toContain("Average of 1 mapped field score");
    expect(wrapper.findAll("tbody tr")[1].findAll("td")[4].find("button").attributes("title")).toContain("Mapping issues are counted separately: 1");

    // Click first product row to open drawer
    const rows = wrapper.findAll("tbody tr");
    expect(rows.length).toBeGreaterThanOrEqual(2);
    await rows[0].trigger("click");
    await flushPromises();

    // Table tooltip closes when opening the drawer so it does not linger over the drawer
    expect(wrapper.text()).not.toContain("How mapping confidence is built");
    expect(mappingDefinitionHelp.attributes("aria-expanded")).toBe("false");

    // Internal provenance does not appear in the routine product-review drawer.
    expect(wrapper.text()).not.toContain("Field Evidence & Provenance");
    expect(wrapper.text()).toContain("Substance A");

    // Click second product row
    await rows[1].trigger("click");
    await flushPromises();

    // Verify drawer now shows second line
    expect(wrapper.text()).toContain("Substance B");
    expect(wrapper.text()).toContain("LowerConfidenceItem");
    expect(wrapper.text()).toContain("Active ingredient requires confirmation");
    expect(wrapper.text()).toContain("1 mapping issue");
    expect(wrapper.text()).toContain("View details");
    expect(wrapper.text()).not.toContain("below full mapping confidence");
    const mappingHelp = wrapper.get('[aria-labelledby="product-drawer-title"] button[aria-label="Explain mapping confidence"]');
    await mappingHelp.trigger("click");
    expect(wrapper.text()).toContain("Average of 1 mapped field score");
    expect(wrapper.text()).toContain("Mapping issues are counted separately: 1");

    // Clicking outside closes the drawer tooltip
    window.document.body.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await flushPromises();
    expect(mappingHelp.attributes("aria-expanded")).toBe("false");
    expect(wrapper.text()).not.toContain("Average of 1 mapped field score");
  });

  it("closes tooltips when clicking outside, pressing Escape, or navigating", async () => {
    const doc = {
      id: "doc-tooltip-test",
      filename: "quotation.pdf",
      source_name: "Tooltip Test Doc",
      status: "pending_review",
      source_system: "pdf",
      quotation: {
        supplier: { name: "Pharma Co" },
        quotation_reference: "Q-123",
        commercial_terms: { currency: "USD", incoterm: "FOB" },
        line_items: [
          {
            product: { trade_name: "Item 1", inn: ["Ingredient 1"], dosage_form: "capsule" },
            quantity: { quoted_quantity: 50 },
            pricing: { currency: "USD", quoted_price: { amount: 5 } },
            source_provenance: {},
          },
          {
            product: { trade_name: "Item 2", inn: ["Ingredient 2"], dosage_form: "tablet" },
            quantity: { quoted_quantity: 100 },
            pricing: { currency: "USD", quoted_price: { amount: 10 } },
            source_provenance: {},
          },
        ],
        field_reviews: [{
          field_path: "line_items[0].source_key",
          mapping_confidence_band: "High",
          mapping_confidence_score: 100,
          mapping_confidence_reason: "the source explicitly identifies this value as this field",
        }, {
          field_path: "line_items[0].product.trade_name",
          mapping_confidence_band: null,
          mapping_confidence_score: null,
          mapping_confidence_reason: "the value was mapped, but its precise source provenance was not recorded",
        }],
      },
      extraction_confidence: { score: 88, band: "High", factors: [] },
      mapping_confidence: { score: 92, band: "High", issue_count: 0 },
      mapping_issues: [],
      reviews: [],
    };
    api.fetchDocuments.mockResolvedValue([doc]);
    const wrapper = mount(App);
    await flushPromises();

    // 1. SourceTable mapping tooltip dismisses on outside click and Escape
    const sourceMappingBtn = wrapper.get('td button[aria-label="Explain mapping confidence"]');
    await sourceMappingBtn.trigger("click");
    expect(sourceMappingBtn.attributes("aria-expanded")).toBe("true");
    expect(wrapper.text()).toContain("This is the average confidence");

    // Outside click closes it
    window.document.body.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await flushPromises();
    expect(sourceMappingBtn.attributes("aria-expanded")).toBe("false");
    expect(wrapper.text()).not.toContain("This is the average confidence");

    // Open again, Escape closes it
    await sourceMappingBtn.trigger("click");
    expect(sourceMappingBtn.attributes("aria-expanded")).toBe("true");
    window.document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await flushPromises();
    expect(sourceMappingBtn.attributes("aria-expanded")).toBe("false");

    // Open the source detail
    await wrapper.get("button.group").trigger("click");
    await flushPromises();

    const productRows = wrapper.findAll("tbody tr");
    expect(productRows).toHaveLength(2);
    expect(productRows[0].findAll("td")[4].text()).toContain("100%");
    expect(productRows[1].findAll("td")[4].text()).toContain("—");

    // 2. ProductTable tooltip dismisses on Escape and outside click
    const tableMappingHelp = wrapper.get('button[aria-label="How mapping confidence is calculated"]');
    await tableMappingHelp.trigger("click");
    expect(tableMappingHelp.attributes("aria-expanded")).toBe("true");
    expect(wrapper.text()).toContain("How mapping confidence is built");

    window.document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await flushPromises();
    expect(tableMappingHelp.attributes("aria-expanded")).toBe("false");
    expect(wrapper.text()).not.toContain("How mapping confidence is built");

    // 3. Row mapping confidence tooltip dismisses on outside click
    const rowMappingBtn = wrapper.findAll("tbody tr")[0].findAll("td")[4].find("button");
    await rowMappingBtn.trigger("click");
    expect(rowMappingBtn.attributes("aria-expanded")).toBe("true");

    window.document.body.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await flushPromises();
    expect(rowMappingBtn.attributes("aria-expanded")).toBe("false");
  });

  it("does not call openImageExtractionForReview or display error banner when image attempts are failed", async () => {
    const failedDoc = {
      id: "failed-glare-doc",
      filename: "scan_03_glare.jpg",
      source_name: "Glare quotation",
      status: "failed",
      failure_reason: "Image scan failed OCR quality checks due to low text clarity or severe glare.",
      source_system: "image",
      reviews: [],
      quotation: null,
      image_extraction_attempts: [
        {
          approach: "ocr_assisted",
          status: "failed",
          failure_reason: "Image scan failed OCR quality checks due to low text clarity or severe glare.",
          product_count: 0,
        },
        {
          approach: "vision_direct",
          status: "failed",
          failure_reason: "Direct vision extraction failed to detect quotation table.",
          product_count: 0,
        },
      ],
    };
    api.fetchDocuments.mockResolvedValue([failedDoc]);

    const wrapper = mount(App);
    await flushPromises();

    // Click into source detail
    await wrapper.get("button.group").trigger("click");
    await flushPromises();

    // It should NOT call openImageExtractionForReview because attempts are failed
    expect(api.openImageExtractionForReview).not.toHaveBeenCalled();
    // It should NOT display the false-positive 409 error banner
    expect(wrapper.text()).not.toContain("This image extraction result is not available for review.");
    // It should display the calm Unclear notice and tags
    expect(wrapper.text()).toContain("Extraction failed");
    expect(wrapper.text()).toContain("Image scan failed OCR quality checks");
    expect(wrapper.text()).toContain("Unclear");
    expect(wrapper.text()).not.toContain("1 failed");
  });

  it("shows retained image material inline for an auto-rejected source without opening review", async () => {
    api.fetchDocuments.mockResolvedValue([{
      id: "unusable-image",
      filename: "glare.jpg",
      source_name: "Glare quotation",
      status: "auto_rejected",
      source_system: "image",
      failure_reason: "Material is not readable enough to use safely.",
      quotation: null,
      reviews: [],
      image_extraction_attempts: [
        { approach: "ocr_assisted", status: "completed", product_count: 0, result: { line_items: [] } },
        { approach: "vision_direct", status: "completed", product_count: 0, result: { line_items: [] } },
      ],
    }]);

    const wrapper = mount(App);
    await flushPromises();
    await wrapper.get("button.group").trigger("click");
    await flushPromises();

    const material = wrapper.get('[aria-label="Original source material"]');
    expect(material.get("img").attributes("src")).toBe("/api/v1/documents/unusable-image/source");
    expect(wrapper.text()).toContain("Material unusable");
    expect(wrapper.text()).not.toContain("This image extraction result has no products to review.");
    expect(api.openImageExtractionForReview).not.toHaveBeenCalled();
  });

  it("opens and closes the How It Works pipeline and confidence guide modal from header, home table, and detail view", async () => {
    api.fetchDocuments.mockResolvedValue([{
      id: "doc-guide",
      filename: "quotation.pdf",
      source_name: "Quotation guide",
      status: "pending_review",
      source_system: "pdf",
      quotation: {
        supplier: {},
        commercial_terms: {},
        line_items: [{ product: { trade_name: "Amox", inn: ["amoxicillin"] }, quantity: {}, pricing: { quoted_price: {} }, packaging: {}, supply: {}, regulatory: {} }],
        revision: 1,
        system_decision: "pending_review",
        review_status: "pending_review",
        review_issues: []
      },
      reviews: [],
    }]);

    const wrapper = mount(App);
    await flushPromises();

    expect(wrapper.text()).not.toContain("How It Works: Pipeline & Confidence Engine");

    // 1. Open from Home table button
    const homeGuideBtn = wrapper.findAll("button").find((btn) => btn.text() === "How it works");
    expect(homeGuideBtn).toBeDefined();
    await homeGuideBtn?.trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("How It Works: Pipeline & Confidence Engine");

    // Close
    let closeBtn = wrapper.findAll("button").find((btn) => btn.text().includes("Got it, close guide"));
    await closeBtn?.trigger("click");
    await flushPromises();
    expect(wrapper.text()).not.toContain("How It Works: Pipeline & Confidence Engine");

    // Open document to navigate to Source Detail page
    await wrapper.get("button.group").trigger("click");
    await flushPromises();

    // 2. Open from Detail page header button
    const detailGuideBtn = wrapper.findAll("button").find((btn) => btn.text().includes("How it works"));
    expect(detailGuideBtn).toBeDefined();
    await detailGuideBtn?.trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("How It Works: Pipeline & Confidence Engine");

    // Switch to scoring tab
    const scoringTab = wrapper.findAll("button").find((btn) => btn.text().includes("Confidence Calculations"));
    await scoringTab?.trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("The 5-Tier Deterministic Provenance Hierarchy");
    expect(wrapper.text()).toContain("Tier 1");
    expect(wrapper.text()).toContain("Tier 3");
    expect(wrapper.text()).toContain("82% (Medium)");
    expect(wrapper.text()).toContain("Commercial Math Bonus (+5%)");

    // Close
    closeBtn = wrapper.findAll("button").find((btn) => btn.text().includes("Got it, close guide"));
    await closeBtn?.trigger("click");
    await flushPromises();
    expect(wrapper.text()).not.toContain("How It Works: Pipeline & Confidence Engine");

    // 3. Open from global top header
    const headerGuideBtn = wrapper.get("#how-it-works-btn");
    await headerGuideBtn.trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("How It Works: Pipeline & Confidence Engine");
  });
});
