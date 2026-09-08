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
    expect(ingestButton?.classes()).toContain("bg-[#261c7a]");
    expect(ingestButton?.classes()).toContain("text-white");
    expect(ingestButton?.element.closest("header")).toBeNull();
    expect(api.fetchDocuments).toHaveBeenCalledOnce();
  });

  it("exports the loaded source and product data as a CSV", async () => {
    api.fetchDocuments.mockResolvedValue([{
      id: "export-source", filename: "offer.json", status: "pending_review", source_system: "json",
      quotation: { supplier: {}, commercial_terms: {}, line_items: [], revision: 1, system_decision: "pending_review", review_status: "pending_review", review_issues: [] },
      reviews: [],
    }]);
    const createObjectURL = vi.fn(() => "blob:export");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);

    const wrapper = mount(App);
    await flushPromises();
    await wrapper.get("button").trigger("click");
    await flushPromises();

    expect(wrapper.findAll("button").find((button) => button.text() === "Export CSV")).toBeDefined();
    expect(createObjectURL).toHaveBeenCalledOnce();
    expect(click).toHaveBeenCalledOnce();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:export");
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
    expect(wrapper.text()).toContain("andina.pdf");
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
            currency: "USD",
            quoted_price: { amount: "0.05", uom: "capsule" },
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
    expect(wrapper.findAll("a").filter((link) => link.text() === "andina.pdf" && link.attributes("download") === "andina.pdf")).toHaveLength(1);
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
    expect(rows[0].findAll("td")[2].text()).toContain("No issues");
    expect(rows[0].findAll("td")[2].text()).not.toContain("—");
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

    await wrapper.get("button").trigger("click");
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
    expect(wrapper.findAll("a").filter((link) => ["first.json", "second.json"].includes(link.text()))).toHaveLength(2);
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
    expect(wrapper.text()).toContain("Mapping issues");
    const mappingDefinitionHelp = wrapper.get('button[aria-label="How mapping confidence is calculated"]');
    await mappingDefinitionHelp.trigger("click");
    expect(wrapper.text()).toContain("How mapping confidence is built");
    expect(wrapper.text()).toContain("The product score is the average of those field scores.");
    expect(wrapper.text()).toContain("Low");
    expect(wrapper.findAll("tbody tr")[1].findAll("td")[5].text().trim()).toBe("1");
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
        ],
        field_reviews: [],
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
});
