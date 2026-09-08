/** Domain type definitions for Axmed Document Intelligence. */

// --- Section 1: Provenance & Evidence Types ---


/**
 * Audit trail record linking an extracted field to its source coordinates and confidence score.
 */
export type Evidence = {
  canonical_field: string;
  source_path?: string | null;
  extraction_method: string;
  confidence: string;
};

// --- Section 2: Quotation Line Items & Pharmaceutical Specs ---

/**
 * Extracted pharmaceutical product line item unifying identity, packaging, pricing, supply, and regulatory data.
 */
export type LineItem = {
  source_key?: string | null;
  product: {
    trade_name?: string | null;
    inn: string[];
    strength: Array<{
      ingredient?: string | null;
      value?: string | null;
      unit?: string | null;
      per_value?: string | null;
      per_unit?: string | null;
    }>;
    dosage_form?: string | null;
    manufacturer?: string | null;
    country_of_origin?: string | null;
  };
  packaging: {
    description?: string | null;
    presentation?: string | null;
    primary_pack?: string | null;
    units_per_pack?: number | null;
    unit_label?: string | null;
    packs_per_shipper?: number | null;
  };
  quantity: {
    quoted_quantity?: string | null;
    quoted_quantity_uom?: string | null;
    quantity_basis?: string | null;
    minimum_order_quantity?: string | null;
    minimum_order_quantity_uom?: string | null;
  };
  pricing: {
    currency?: string | null;
    pack_price?: string | null;
    quoted_price: { amount?: string | null; uom?: string | null };
    normalized_price: {
      amount?: string | null;
      uom?: string | null;
      calculation?: string | null;
      derived?: boolean;
      validation_status?: string | null;
    };
    discount?: string | null;
    extended_price?: string | null;
    price_tiers?: Array<{
      min_quantity?: string | null;
      max_quantity?: string | null;
      quantity_uom?: string | null;
      price?: string | null;
      price_uom?: string | null;
    }>;
    adjustments?: Array<{
      type: string;
      value?: string | null;
      value_type?: string | null;
      condition?: string | null;
    }>;
  };
  supply: {
    lead_time_days?: number | null;
    lead_time_min_days?: number | null;
    lead_time_max_days?: number | null;
    shelf_life_months?: number | null;
    minimum_remaining_shelf_life_percent?: string | null;
    storage_conditions?: string | null;
    cold_chain_required?: boolean | null;
  };
  regulatory: {
    who_prequalified?: boolean | null;
    who_pq_reference?: string | null;
    registered_markets?: string[];
    registration_reference?: string | null;
    regulatory_status?: string | null;
  };
  evidence: Evidence[];
};

// --- Section 3: Canonical Quotation Aggregates ---

/**
 * Top-level canonical quotation schema aggregating all extracted products, terms, and review states.
 */
export type Quotation = {
  quotation_reference?: string | null;
  rfq_reference?: string | null;
  document_type?: string | null;
  supplier: { name?: string | null; country?: string | null };
  commercial_terms: {
    currency?: string | null;
    incoterm?: string | null;
    incoterm_named_place?: string | null;
    incoterm_country?: string | null;
    payment_terms?: string | null;
    price_basis?: string | null;
    transit_time_days?: number | null;
    transit_time_min_days?: number | null;
    transit_time_max_days?: number | null;
    hs_codes?: string[];
  };
  line_items: LineItem[];
  field_reviews?: Array<{
    field_path: string;
    value: unknown;
    review_status: string;
    mapping_confidence_band: "High" | "Medium" | "Low" | null;
    mapping_confidence_score: number | null;
    mapping_confidence_reason?: string | null;
    /** Raw source-evidence score retained for extraction-quality audit. */
    source_evidence_score: string;
    extraction_method: string;
    source_path?: string | null;
    source_location?: string | null;
  }>;
  revision: number;
  system_decision: "pending_review";
  review_status: "pending_review" | "approved" | "rejected";
  has_corrections?: boolean;
  review_issues: Array<{ field_path: string; code: string; message: string; severity: string }>;
};

// --- Section 4: Ingestion Documents & Peer Extractions ---

/**
 * Peer extraction attempt from multimodal image intake (OCR-assisted or vision-direct).
 */
export type ImageExtractionAttempt = {
  approach: "ocr_assisted" | "vision_direct" | string;
  status: "completed" | "failed" | string;
  result: {
    quotation_reference?: string | null;
    supplier: { name?: string | null; country?: string | null };
    line_items: LineItem[];
    review_issues?: Array<{ field_path: string; code: string; message: string; severity: string }>;
  } | null;
  product_count: number;
  failure_reason?: string | null;
  provider?: string | null;
  model?: string | null;
  duration_ms?: number | null;
  extraction_confidence?: DocumentResponse["extraction_confidence"];
  mapping_confidence?: DocumentResponse["mapping_confidence"];
};

/**
 * Primary document record returned by the backend API.
 */
export type DocumentResponse = {
  id: string;
  filename: string;
  source_name?: string | null;
  status: "pending_extraction" | "pending_review" | "approved" | "rejected" | "failed" | string;
  failure_reason?: string | null;
  source_system?: string | null;
  schema_version?: string | null;
  parsed_summary?: {
    subject?: string;
    message_id?: string | null;
    page_count?: number;
    needs_ocr_pages?: number[];
  } | null;
  system_decision?: "pending_review" | null;
  extraction_confidence?: {
    score: number;
    band: "High" | "Medium" | "Low";
    factors: Array<{ key: string; label: string; weight: number; score: number; reason: string }>;
  };
  mapping_confidence?: {
    score: number | null;
    band: "High" | "Medium" | "Low" | null;
    issue_count: number;
  } | null;
  mapping_issues?: Array<{
    field_path: string;
    section: "document" | "product" | "pricing" | "quantity_packaging" | "supply" | "regulatory" | string;
    code: string;
    message: string;
    severity: string;
  }>;
  product_counts?: { extracted: number; failed: number };
  notes?: string[];
  extracted_source_facts?: Array<{
    label: string;
    value: unknown;
    source_path: string;
    extraction_method: string;
    confidence: string;
    confidence_reason?: string | null;
    normalization_status: "mapped" | "unmapped" | string;
    canonical_field?: string | null;
    review_status: string;
  }>;
  quotation?: Quotation | null;
  reviews: Array<{
    action: string;
    prior_revision: number;
    resulting_revision: number;
    note?: string | null;
    rejection_reason?: string | null;
    patches: Array<{ path: string; before?: string | null; after?: string | null }>;
  }>;
  ocr?: { id: string; status: string; selected_pages: number[] } | null;
  image_extraction_attempts?: ImageExtractionAttempt[];
  source_result?: "ocr_assisted" | "vision_direct" | string;
};

// --- Section 5: Processing Events & SSE Contracts ---

/**
 * Real-time event emitted during asynchronous processing and received via SSE.
 */
export type ProcessingEvent = {
  id: number;
  document_id: string;
  stage: string;
  phase: string;
  message: string;
  metadata: Record<string, unknown>;
  created_at?: string | null;
};
