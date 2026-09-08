import type { DocumentResponse, LineItem } from "@/types";

const sourceHeaders = [
  "record_type", "source_id", "source_file", "source_status", "source_system", "failure_reason", "source_notes",
  "extraction_confidence", "mapping_confidence", "mapping_issue_count", "quotation_reference", "supplier", "commercial_currency",
];
const productHeaders = [
  "product_position", "product", "active_ingredients", "strengths", "dosage_form", "manufacturer", "country_of_origin",
  "quoted_quantity", "quoted_quantity_uom", "quantity_basis", "minimum_order_quantity", "minimum_order_quantity_uom",
  "currency", "quoted_price", "quoted_price_uom", "pack_price", "discount", "extended_price",
  "normalized_price", "normalized_price_uom", "price_tiers", "adjustments", "packaging_description", "presentation",
  "primary_pack", "units_per_pack", "unit_label", "packs_per_shipper", "lead_time_days", "lead_time_min_days",
  "lead_time_max_days", "shelf_life_months", "storage_conditions", "cold_chain_required", "who_prequalified",
  "who_pq_reference", "registered_markets", "registration_reference", "regulatory_status",
];
const factHeaders = [
  "fact_label", "fact_value", "fact_source_path", "fact_extraction_method", "fact_confidence", "fact_confidence_reason",
  "fact_normalization_status", "fact_canonical_field", "fact_review_status",
];
const issueHeaders = ["issue_field_path", "issue_section", "issue_code", "issue_message", "issue_severity"];
const reviewHeaders = ["review_action", "review_prior_revision", "review_resulting_revision", "review_note", "review_rejection_reason", "review_patches"];
const headers = [...sourceHeaders, ...productHeaders, ...factHeaders, ...issueHeaders, ...reviewHeaders];

function cell(value: unknown): string {
  const text = value == null ? "" : String(value);
  return `"${text.replaceAll('"', '""')}"`;
}

function blanks(count: number): unknown[] {
  return Array(count).fill("");
}

function sourceValues(document: DocumentResponse, recordType: string): unknown[] {
  const quotation = document.quotation;
  return [
    recordType, document.id, document.filename, document.status, document.source_system, document.failure_reason,
    document.notes?.join(" | "), document.extraction_confidence?.score, document.mapping_confidence?.score,
    document.mapping_confidence?.issue_count ?? 0, quotation?.quotation_reference, quotation?.supplier.name,
    quotation?.commercial_terms.currency,
  ];
}

function strengthSummary(item: LineItem): string {
  return item.product.strength
    .map((strength) => [strength.ingredient, strength.value, strength.unit, strength.per_value && `/ ${strength.per_value} ${strength.per_unit ?? ""}`].filter(Boolean).join(" "))
    .join("; ");
}

function productValues(item: LineItem, position: number): unknown[] {
  return [
    position + 1, item.product.trade_name, item.product.inn.join("; "), strengthSummary(item), item.product.dosage_form,
    item.product.manufacturer, item.product.country_of_origin, item.quantity.quoted_quantity, item.quantity.quoted_quantity_uom,
    item.quantity.quantity_basis, item.quantity.minimum_order_quantity, item.quantity.minimum_order_quantity_uom,
    item.pricing.currency, item.pricing.quoted_price.amount, item.pricing.quoted_price.uom, item.pricing.pack_price,
    item.pricing.discount, item.pricing.extended_price, item.pricing.normalized_price.amount, item.pricing.normalized_price.uom,
    JSON.stringify(item.pricing.price_tiers ?? []), JSON.stringify(item.pricing.adjustments ?? []), item.packaging.description,
    item.packaging.presentation, item.packaging.primary_pack, item.packaging.units_per_pack, item.packaging.unit_label,
    item.packaging.packs_per_shipper, item.supply.lead_time_days, item.supply.lead_time_min_days, item.supply.lead_time_max_days,
    item.supply.shelf_life_months, item.supply.storage_conditions, item.supply.cold_chain_required,
    item.regulatory.who_prequalified, item.regulatory.who_pq_reference, item.regulatory.registered_markets?.join("; "),
    item.regulatory.registration_reference, item.regulatory.regulatory_status,
  ];
}

/** Includes every available representation for each uploaded source. */
export function documentsToCsv(documents: DocumentResponse[]): string {
  const rows: unknown[][] = [];
  for (const document of documents) {
    rows.push([...sourceValues(document, "source"), ...blanks(productHeaders.length + factHeaders.length + issueHeaders.length + reviewHeaders.length)]);
    for (const [position, item] of (document.quotation?.line_items ?? []).entries()) {
      rows.push([...sourceValues(document, "product"), ...productValues(item, position), ...blanks(factHeaders.length + issueHeaders.length + reviewHeaders.length)]);
    }
    for (const fact of document.extracted_source_facts ?? []) {
      rows.push([
        ...sourceValues(document, "source_fact"), ...blanks(productHeaders.length), fact.label, JSON.stringify(fact.value),
        fact.source_path, fact.extraction_method, fact.confidence, fact.confidence_reason, fact.normalization_status,
        fact.canonical_field, fact.review_status, ...blanks(issueHeaders.length + reviewHeaders.length),
      ]);
    }
    for (const issue of document.mapping_issues ?? []) {
      rows.push([
        ...sourceValues(document, "mapping_issue"), ...blanks(productHeaders.length + factHeaders.length), issue.field_path,
        issue.section, issue.code, issue.message, issue.severity, ...blanks(reviewHeaders.length),
      ]);
    }
    for (const review of document.reviews) {
      rows.push([
        ...sourceValues(document, "review"), ...blanks(productHeaders.length + factHeaders.length + issueHeaders.length),
        review.action, review.prior_revision, review.resulting_revision, review.note, review.rejection_reason,
        JSON.stringify(review.patches),
      ]);
    }
  }
  return [headers, ...rows].map((row) => row.map(cell).join(",")).join("\r\n");
}
