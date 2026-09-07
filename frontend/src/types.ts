export type Evidence = {
  canonical_field: string;
  source_path?: string | null;
  extraction_method: string;
  confidence: string;
};

export type LineItem = {
  source_key?: string | null;
  product: {
    trade_name?: string | null;
    inn: string[];
    strength: Array<{ ingredient?: string | null; value?: string | null; unit?: string | null; per_value?: string | null; per_unit?: string | null }>;
    dosage_form?: string | null;
    route?: string | null;
    manufacturer?: string | null;
    country_of_origin?: string | null;
  };
  packaging: { description?: string | null; presentation?: string | null; primary_pack?: string | null; units_per_pack?: number | null; unit_label?: string | null; packs_per_shipper?: number | null };
  quantity: { quoted_quantity?: string | null; quoted_quantity_uom?: string | null; quantity_basis?: string | null; minimum_order_quantity?: string | null; minimum_order_quantity_uom?: string | null };
  pricing: {
    currency?: string | null;
    pack_price?: string | null;
    quoted_price: { amount?: string | null; uom?: string | null };
    normalized_price: { amount?: string | null; uom?: string | null; calculation?: string | null; derived?: boolean; validation_status?: string | null };
    discount?: string | null;
    extended_price?: string | null;
    price_tiers?: Array<{ min_quantity?: string | null; max_quantity?: string | null; quantity_uom?: string | null; price?: string | null; price_uom?: string | null }>;
    adjustments?: Array<{ type: string; value?: string | null; value_type?: string | null; condition?: string | null }>;
  };
  supply: { lead_time_days?: number | null; shelf_life_months?: number | null; minimum_remaining_shelf_life_percent?: string | null; storage_conditions?: string | null; cold_chain_required?: boolean | null };
  regulatory: { who_prequalified?: boolean | null; who_pq_reference?: string | null; registered_markets?: string[]; registration_reference?: string | null; regulatory_status?: string | null; hs_code?: string | null; atc_code?: string | null };
  evidence: Evidence[];
};

export type Quotation = {
  quotation_reference?: string | null;
  document_type?: string | null;
  supplier: { name?: string | null; country?: string | null };
  commercial_terms: { currency?: string | null; incoterm?: string | null; incoterm_named_place?: string | null };
  line_items: LineItem[];
  field_reviews?: Array<{
    field_path: string;
    value: unknown;
    review_status: string;
    confidence_band: "High" | "Medium" | "Low" | null;
    confidence_reason?: string | null;
    /** Raw evidence score retained for audit/evaluation; not user-facing confidence. */
    confidence: string;
    extraction_method: string;
    source_path?: string | null;
    source_location?: string | null;
  }>;
  revision: number;
  system_decision: "auto_accepted" | "needs_review";
  review_status: string;
  review_issues: Array<{ field_path: string; code: string; message: string; severity: string }>;
};

export type DocumentResponse = {
  id: string;
  batch_id?: string | null;
  filename: string;
  source_name?: string | null;
  status: "needs_mapping_confirmation" | "needs_mapping_resolution" | "needs_review" | "failed" | string;
  failure_reason?: string | null;
  source_system?: string | null;
  schema_version?: string | null;
  schema_fingerprint?: string | null;
  semantic_mapping_calls: number;
  mapping_source?: string | null;
  parsed_summary?: { subject?: string; message_id?: string | null; page_count?: number; needs_ocr_pages?: number[] } | null;
  system_decision?: "auto_accepted" | "needs_review" | null;
  extraction_coverage?: { extracted: number; expected: number } | null;
  confidence_summary?: Record<"High" | "Medium" | "Low", number>;
  review_reasons?: string[];
  product_counts?: { extracted: number; failed: number };
  notes?: string[];
  mapping?: {
    id: string;
    trust_state: string;
    times_seen: number;
    times_confirmed: number;
    human_verified: boolean;
  } | null;
  quotation?: Quotation | null;
  reviews: Array<{
    action: string;
    prior_revision: number;
    resulting_revision: number;
    note?: string | null;
    rejection_reason?: string | null;
    patches: Array<{ path: string; before?: string | null; after?: string | null }>;
  }>;
  learning?: Array<{ id: string; review_id: string; status: string }>;
  ocr?: { id: string; status: string; selected_pages: number[] } | null;
};

export type ProcessingEvent = {
  id: number;
  document_id: string;
  learning_id?: string | null;
  stage: string;
  phase: string;
  message: string;
  metadata: Record<string, unknown>;
  created_at?: string | null;
};

export type BatchResponse = {
  id: string;
  name: string;
  created_at: string | null;
  updated_at: string | null;
  total_documents: number;
  status_counts: Record<string, number>;
  is_completed: boolean;
  documents: DocumentResponse[];
};

export type EvaluationCase = {
  id: string;
  title: string;
  rubric: Array<{ id: string; label: string; success_criterion: string }>;
};

export type EvaluationRun = {
  id: string;
  status: string;
  execution_mode: string;
  created_at: string;
  summary: { case_count: number; passed: number; rubrics: EvaluationCase["rubric"] };
  results: Array<{
    case_id: string;
    status: string;
    scores: Record<string, number | string>;
    errors: string[];
  }>;
};

export type EvaluationsResponse = { cases: EvaluationCase[]; runs: EvaluationRun[] };
