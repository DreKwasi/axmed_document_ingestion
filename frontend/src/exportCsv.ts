/** User-facing CSV export for terminal supplier sources and extracted products. */

import type { DocumentResponse, LineItem } from "@/types";

const sourceHeaders = [
  "source_file", "file_format", "failure_reason", "source_notes", "extraction_confidence",
  "extraction_confidence_explanation", "mapping_confidence", "mapping_issue_count",
  "quotation_reference", "supplier", "commercial_currency",
];

const productHeaders = [
  "product_position", "product", "active_ingredients", "strengths", "dosage_form", "manufacturer",
  "country_of_origin", "quoted_quantity", "quoted_quantity_uom", "minimum_order_quantity",
  "minimum_order_quantity_uom", "quoted_price", "quoted_price_uom", "pack_price", "discount",
  "extended_price", "normalized_price", "normalized_price_uom", "price_tiers", "adjustments",
  "packaging_description", "units_per_pack", "unit_label", "packs_per_shipper", "lead_time_days",
  "lead_time_min_days", "lead_time_max_days", "shelf_life_months", "storage_conditions",
  "cold_chain_required", "who_prequalified", "who_pq_reference", "registered_markets",
  "registration_reference", "regulatory_status",
];

const issueHeaders = ["issue_field_path", "issue_section", "issue_code", "issue_message", "issue_severity"];
const reviewHeaders = [
  "review_action", "review_prior_revision", "review_resulting_revision", "review_note",
  "review_rejection_reason", "review_patches",
];
const headers = [...sourceHeaders, ...productHeaders, ...issueHeaders, ...reviewHeaders];
const terminalStatuses = new Set([
  "pending_review", "approved", "rejected", "failed", "completed", "corrected", "needs_review", "auto_accepted",
]);

function cell(value: unknown): string {
  const text = value == null ? "" : String(value);
  return `"${text.replaceAll('"', '""')}"`;
}

function fileFormat(filename: string): string {
  const extension = filename.split(".").pop();
  return extension && extension !== filename ? extension.toUpperCase() : "FILE";
}

function extractionConfidenceExplanation(document: DocumentResponse): string {
  return (document.extraction_confidence?.factors ?? [])
    .map((factor) => `${factor.label}: ${factor.reason}`)
    .join(" | ");
}

function sourceValues(document: DocumentResponse, item?: LineItem): unknown[] {
  const quotation = document.quotation;
  return [
    document.filename,
    fileFormat(document.filename),
    document.failure_reason,
    document.notes?.join(" | "),
    document.extraction_confidence?.score,
    extractionConfidenceExplanation(document),
    document.mapping_confidence?.score,
    document.mapping_confidence?.issue_count ?? 0,
    quotation?.quotation_reference,
    quotation?.supplier.name,
    quotation?.commercial_terms.currency ?? item?.pricing.currency,
  ];
}

function strengthSummary(item: LineItem): string {
  return item.product.strength
    .map((strength) => [
      strength.ingredient,
      strength.value,
      strength.unit,
      strength.per_value && `/ ${strength.per_value} ${strength.per_unit ?? ""}`,
    ].filter(Boolean).join(" "))
    .join("; ");
}

function productValues(item?: LineItem, position?: number): unknown[] {
  if (!item || position == null) return Array(productHeaders.length).fill("");
  return [
    position + 1, item.product.trade_name, item.product.inn.join("; "), strengthSummary(item),
    item.product.dosage_form, item.product.manufacturer, item.product.country_of_origin,
    item.quantity.quoted_quantity, item.quantity.quoted_quantity_uom, item.quantity.minimum_order_quantity,
    item.quantity.minimum_order_quantity_uom, item.pricing.quoted_price.amount, item.pricing.quoted_price.uom,
    item.pricing.pack_price, item.pricing.discount, item.pricing.extended_price,
    item.pricing.normalized_price.amount, item.pricing.normalized_price.uom,
    JSON.stringify(item.pricing.price_tiers ?? []), JSON.stringify(item.pricing.adjustments ?? []),
    item.packaging.description, item.packaging.units_per_pack, item.packaging.unit_label,
    item.packaging.packs_per_shipper, item.supply.lead_time_days, item.supply.lead_time_min_days,
    item.supply.lead_time_max_days, item.supply.shelf_life_months, item.supply.storage_conditions,
    item.supply.cold_chain_required, item.regulatory.who_prequalified, item.regulatory.who_pq_reference,
    item.regulatory.registered_markets?.join("; "), item.regulatory.registration_reference,
    item.regulatory.regulatory_status,
  ];
}

function appliesToProduct(fieldPath: string, position: number): boolean {
  if (!fieldPath.startsWith("line_items")) return true;
  return fieldPath.startsWith(`line_items[${position}]`) || fieldPath.startsWith(`line_items.${position}.`);
}

function aggregate(values: Array<string | null | undefined>): string {
  return [...new Set(values.filter((value): value is string => Boolean(value)))].join("; ");
}

function issueValues(document: DocumentResponse, position?: number): unknown[] {
  const issues = (document.mapping_issues ?? []).filter(
    (issue) => position == null || appliesToProduct(issue.field_path, position)
  );
  return [
    aggregate(issues.map((issue) => issue.field_path)), aggregate(issues.map((issue) => issue.section)),
    aggregate(issues.map((issue) => issue.code)), aggregate(issues.map((issue) => issue.message)),
    aggregate(issues.map((issue) => issue.severity)),
  ];
}

function reviewValues(document: DocumentResponse): unknown[] {
  return [
    aggregate(document.reviews.map((review) => review.action)),
    aggregate(document.reviews.map((review) => String(review.prior_revision))),
    aggregate(document.reviews.map((review) => String(review.resulting_revision))),
    aggregate(document.reviews.map((review) => review.note)),
    aggregate(document.reviews.map((review) => review.rejection_reason)),
    document.reviews.length ? JSON.stringify(document.reviews.flatMap((review) => review.patches)) : "",
  ];
}

/** Serializes terminal sources into one row per product, with one summary row when no product exists. */
export function documentsToCsv(documents: DocumentResponse[]): string {
  const rows: unknown[][] = [];
  for (const document of documents.filter((candidate) => terminalStatuses.has(candidate.status))) {
    const items = document.quotation?.line_items ?? [];
    if (!items.length) {
      rows.push([
        ...sourceValues(document), ...productValues(), ...issueValues(document), ...reviewValues(document),
      ]);
      continue;
    }
    for (const [position, item] of items.entries()) {
      rows.push([
        ...sourceValues(document, item), ...productValues(item, position), ...issueValues(document, position),
        ...reviewValues(document),
      ]);
    }
  }
  return [headers, ...rows].map((row) => row.map(cell).join(",")).join("\r\n");
}
