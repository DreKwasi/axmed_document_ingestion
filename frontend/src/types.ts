export type Evidence = {
  canonical_field: string;
  source_path?: string | null;
  extraction_method: string;
  confidence: string;
};

export type LineItem = {
  source_key?: string | null;
  product: { trade_name?: string | null; inn: string[]; dosage_form?: string | null };
  packaging: { primary_pack?: string | null; units_per_pack?: number | null; unit_label?: string | null };
  quantity: { minimum_order_quantity?: string | null; minimum_order_quantity_uom?: string | null };
  pricing: {
    currency?: string | null;
    pack_price?: string | null;
    quoted_price: { amount?: string | null; uom?: string | null };
    normalized_price: { amount?: string | null; uom?: string | null; calculation?: string | null; derived?: boolean };
  };
  supply: { lead_time_days?: number | null };
  evidence: Evidence[];
};

export type Quotation = {
  quotation_reference?: string | null;
  document_type?: string | null;
  supplier: { name?: string | null; country?: string | null };
  commercial_terms: { currency?: string | null; incoterm?: string | null; incoterm_named_place?: string | null };
  line_items: LineItem[];
  revision: number;
  review_status: string;
  review_issues: Array<{ field_path: string; code: string; message: string; severity: string }>;
};

export type DocumentResponse = {
  id: string;
  batch_id?: string | null;
  filename: string;
  status: "needs_mapping_confirmation" | "needs_mapping_resolution" | "needs_review" | "failed" | string;
  failure_reason?: string | null;
  source_system?: string | null;
  schema_version?: string | null;
  schema_fingerprint?: string | null;
  semantic_mapping_calls: number;
  mapping_source?: string | null;
  parsed_summary?: { subject?: string; message_id?: string | null; page_count?: number; needs_ocr_pages?: number[] } | null;
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
    patches: Array<{ path: string; before?: string | null; after?: string | null }>;
  }>;
  learning?: Array<{ id: string; review_id: string; status: string }>;
  ocr?: { id: string; status: string; selected_pages: number[] } | null;
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
