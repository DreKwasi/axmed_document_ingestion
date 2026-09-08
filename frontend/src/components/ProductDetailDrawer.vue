<script setup lang="ts">
/** Product detail drawer for inspecting specs and applying field corrections. */

import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { DocumentResponse, LineItem } from "@/types";

// --- Section 1: Props & Emits ---

const props = defineProps<{
  isOpen: boolean;
  document: DocumentResponse;
  lineItem: LineItem | null;
  lineIndex: number;
  busy: boolean;
}>();

const emit = defineEmits<{
  (event: "close"): void;
  (event: "saveCorrection", payload: { fieldPath: string; value: unknown; lineIndex: number }): void;
}>();

// --- Section 2: Editable Fields ---

type EditableField = { path: string; label: string; kind?: "json" | "boolean" };

const editableFields: EditableField[] = [
  { path: "product.trade_name", label: "Product identity · Trade name" },
  { path: "product.inn", label: "Product identity · Active ingredients (INN)", kind: "json" },
  { path: "product.strength", label: "Product identity · Strength", kind: "json" },
  { path: "product.dosage_form", label: "Product identity · Dosage form" },
  { path: "product.manufacturer", label: "Product identity · Manufacturer" },
  { path: "product.country_of_origin", label: "Product identity · Country of origin" },
  { path: "pricing.currency", label: "Pricing · Currency" },
  { path: "pricing.quoted_price.amount", label: "Pricing · Quoted price" },
  { path: "pricing.quoted_price.uom", label: "Pricing · Quoted price unit" },
  { path: "pricing.pack_price", label: "Pricing · Pack price" },
  { path: "pricing.discount", label: "Pricing · Discount" },
  { path: "pricing.extended_price", label: "Pricing · Extended price" },
  { path: "pricing.price_tiers", label: "Pricing · Price tiers", kind: "json" },
  { path: "pricing.adjustments", label: "Pricing · Adjustments", kind: "json" },
  { path: "quantity.quoted_quantity", label: "Quantity & packaging · Quoted quantity" },
  { path: "quantity.quoted_quantity_uom", label: "Quantity & packaging · Quoted quantity unit" },
  { path: "quantity.quantity_basis", label: "Quantity & packaging · Quantity basis" },
  { path: "quantity.minimum_order_quantity", label: "Quantity & packaging · MOQ" },
  { path: "quantity.minimum_order_quantity_uom", label: "Quantity & packaging · MOQ unit" },
  { path: "packaging.description", label: "Quantity & packaging · Description" },
  { path: "packaging.presentation", label: "Quantity & packaging · Presentation" },
  { path: "packaging.primary_pack", label: "Quantity & packaging · Primary pack" },
  { path: "packaging.units_per_pack", label: "Quantity & packaging · Units per pack" },
  { path: "packaging.unit_label", label: "Quantity & packaging · Unit label" },
  { path: "packaging.packs_per_shipper", label: "Quantity & packaging · Packs per shipper" },
  { path: "supply.lead_time_days", label: "Supply · Lead time" },
  { path: "supply.lead_time_min_days", label: "Supply · Minimum lead time" },
  { path: "supply.lead_time_max_days", label: "Supply · Maximum lead time" },
  { path: "supply.shelf_life_months", label: "Supply · Shelf life" },
  { path: "supply.minimum_remaining_shelf_life_percent", label: "Supply · Minimum remaining shelf life" },
  { path: "supply.storage_conditions", label: "Supply · Storage conditions" },
  { path: "supply.cold_chain_required", label: "Supply · Cold chain required", kind: "boolean" },
  { path: "regulatory.who_prequalified", label: "Regulatory · WHO prequalified", kind: "boolean" },
  { path: "regulatory.who_pq_reference", label: "Regulatory · WHO PQ reference" },
  { path: "regulatory.registered_markets", label: "Regulatory · Registered markets", kind: "json" },
  { path: "regulatory.registration_reference", label: "Regulatory · Registration reference" },
  { path: "regulatory.regulatory_status", label: "Regulatory · Regulatory status" },
];

// --- Section 3: State & Tooltip Controls ---

const selectedField = ref("pricing.pack_price");
const correctionValue = ref("");
const showExtractionCalculation = ref(false);
const showMappingExplanation = ref(false);
const showMappingConcernDefinition = ref(false);
const mappingConcernDefinition =
  "A field score is based on how directly the source identifies the schema field, "
  + "the strength of its source location/provenance, whether the value matches the expected category, "
  + "and whether related values agree. A score below 100% means the evidence is less direct; "
  + "it is not automatically an actionable issue.";

function closeTooltips() {
  showExtractionCalculation.value = false;
  showMappingExplanation.value = false;
  showMappingConcernDefinition.value = false;
}

function handleDocumentClick(event: MouseEvent) {
  const target = event.target as Element | null;
  if (!target) return;
  if (target.closest?.("[data-tooltip-container]")) return;
  closeTooltips();
}

function handleDocumentKeydown(event: KeyboardEvent) {
  if (event.key === "Escape") {
    closeTooltips();
  }
}

onMounted(() => {
  document.addEventListener("click", handleDocumentClick);
  document.addEventListener("keydown", handleDocumentKeydown);
});

onBeforeUnmount(() => {
  document.removeEventListener("click", handleDocumentClick);
  document.removeEventListener("keydown", handleDocumentKeydown);
});

watch(
  [() => props.lineItem, selectedField, () => props.isOpen],
  () => {
    closeTooltips();
    if (!props.lineItem) {
      correctionValue.value = "";
      return;
    }
    correctionValue.value = editableValue(props.lineItem, selectedField.value);
  },
  { immediate: true }
);

// --- Section 4: Display & Precision Formatters ---

function displayValue(value: string | number | boolean | null | undefined): string {
  if (value == null || value === "") return "—";
  if (typeof value === "string" && /^\d{4,}$/.test(value)) return Number(value).toLocaleString();
  return String(value);
}

function decimalPlaces(value: string | null | undefined): number {
  if (!value) return 0;
  const plain = value.toLowerCase().split("e")[0];
  return plain.includes(".") ? plain.split(".")[1].length : 0;
}

function displayPrice(value: string | null | undefined, precisionSource?: string | null): string {
  if (value == null) return "—";
  const numeric = Number(value);
  const maximumFractionDigits = precisionSource == null ? 6 : decimalPlaces(precisionSource);
  return Number.isFinite(numeric) ? numeric.toLocaleString(undefined, { maximumFractionDigits }) : value;
}

function displayLeadTime(supply: LineItem["supply"]): string {
  const minimum = supply.lead_time_min_days;
  const maximum = supply.lead_time_max_days;
  if (minimum != null && maximum != null) return minimum === maximum ? `${minimum} days` : `${minimum}–${maximum} days`;
  if (minimum != null) return `From ${minimum} days`;
  if (maximum != null) return `Up to ${maximum} days`;
  return supply.lead_time_days != null ? `${supply.lead_time_days} days` : "—";
}

const displayTransitDuration = computed(() => {
  const terms = props.document.quotation?.commercial_terms;
  if (!terms) return "—";
  if (terms.transit_time_min_days != null && terms.transit_time_max_days != null) {
    return terms.transit_time_min_days === terms.transit_time_max_days
      ? `${terms.transit_time_min_days} days`
      : `${terms.transit_time_min_days}–${terms.transit_time_max_days} days`;
  }
  if (terms.transit_time_days != null) {
    return `${terms.transit_time_days} days`;
  }
  if (terms.transit_time_min_days != null) {
    return `≥ ${terms.transit_time_min_days} days`;
  }
  if (terms.transit_time_max_days != null) {
    return `≤ ${terms.transit_time_max_days} days`;
  }
  return "—";
});

function humanizeFieldPath(path: string): string {
  const labels: Record<string, string> = {
    "product.country_of_origin": "Country of origin",
    "product.trade_name": "Trade name",
    "product.inn": "Active ingredients",
    "product.strength": "Strength",
    "product.dosage_form": "Dosage form",
    "pricing.quoted_price.amount": "Quoted price",
    "pricing.pack_price": "Pack price",
    "quantity.quoted_quantity": "Quoted quantity",
    "quantity.minimum_order_quantity": "Minimum order quantity",
    "commercial_terms.transit_time_days": "Transit duration",
    "commercial_terms.transit_time_min_days": "Min transit duration",
    "commercial_terms.transit_time_max_days": "Max transit duration",
  };
  if (labels[path]) return labels[path];
  return path
    .split(".")
    .map((part) => part.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase()))
    .join(" · ");
}

// --- Section 5: Mapping & Extraction Confidence ---

const rowMappingConfidence = computed(() => {
  const values = props.document.quotation?.field_reviews
    ?.filter((field) => field.field_path.startsWith(`line_items[${props.lineIndex}]`))
    .map((field) => field.mapping_confidence_score)
    .filter((score): score is number => score != null) ?? [];
  return values.length ? Math.round(values.reduce((sum, score) => sum + score, 0) / values.length) : null;
});

const rowMappingIssueCount = computed(() => (props.document.mapping_issues ?? [])
  .filter((issue) => issue.field_path.startsWith(`line_items[${props.lineIndex}]`)).length);

const rowMappingExplanation = computed(() => {
  const fields = props.document.quotation?.field_reviews
    ?.filter((field) => field.field_path.startsWith(`line_items[${props.lineIndex}]`)) ?? [];
  const scores = fields.map((field) => field.mapping_confidence_score).filter((score): score is number => score != null);
  if (!scores.length) return "No mapped fields are available to assess.";
  const reasons = [...new Set(fields.map((field) => field.mapping_confidence_reason).filter((reason): reason is string => Boolean(reason)))];
  return `Average of ${scores.length} mapped field score${scores.length === 1 ? "" : "s"}: ${rowMappingConfidence.value}%. ${reasons.join(" ")} Mapping issues are counted separately: ${rowMappingIssueCount.value}.`;
});

const extractionFactors = computed(() => props.document.extraction_confidence?.factors ?? []);

const extractionSummary = computed(() => {
  const score = props.document.extraction_confidence?.score;
  if (score == null) return "No extraction result is available to assess.";
  if (score === 100) return "Source content was recovered successfully. No extraction-quality problems were detected.";
  return "Source content was recovered with some uncertainty. See the calculation details for what affected this score.";
});

const extractionCalculation = computed(() => {
  if (!extractionFactors.value.length) return "No calculation details are available.";
  return extractionFactors.value
    .map((factor) => `${factor.label} (${factor.weight}%): ${factor.score}% — ${factor.reason}`)
    .join("\n");
});

function mappingIssuesFor(section: string) {
  const prefix = `line_items[${props.lineIndex}]`;
  return (props.document.mapping_issues ?? []).filter(
    (issue) => issue.field_path.startsWith(prefix) && issue.section === section
  );
}

function mappingConcernsFor(section: string) {
  const prefix = `line_items[${props.lineIndex}]`;
  return (props.document.quotation?.field_reviews ?? [])
    .filter((field) => field.field_path.startsWith(prefix))
    .filter((field) => field.mapping_confidence_score != null && field.mapping_confidence_score < 100)
    .filter((field) => {
      const suffix = field.field_path.slice(`${prefix}.`.length);
      if (suffix.startsWith("product.")) return section === "product";
      if (suffix.startsWith("pricing.")) return section === "pricing";
      if (suffix.startsWith("quantity.") || suffix.startsWith("packaging.")) return section === "quantity_packaging";
      if (suffix.startsWith("supply.")) return section === "supply";
      if (suffix.startsWith("regulatory.")) return section === "regulatory";
      return false;
    })
    .map((field) => ({
      label: humanizeFieldPath(field.field_path.slice(`${prefix}.`.length)),
      score: field.mapping_confidence_score as number,
      reason: reviewerMappingReason(field.mapping_confidence_reason),
    }));
}

function reviewerMappingReason(reason?: string | null): string {
  if (!reason) return "This field has less than full mapping certainty.";
  if (reason.includes("source evidence: usable") && reason.includes("association: limited")) {
    return "The value was found in the source, but the source did not explicitly identify it as this field.";
  }
  if (reason.includes("independent validation: unavailable")) {
    return "No second source value was available to confirm this mapping.";
  }
  return reason;
}

// --- Section 6: Correction Submission ---

function handleSave() {
  if (!correctionValue.value.trim()) return;
  const field = editableFields.find((item) => item.path === selectedField.value);
  let value: unknown = correctionValue.value.trim();
  if (field?.kind === "json") {
    try {
      value = JSON.parse(correctionValue.value);
    } catch {
      return;
    }
  } else if (field?.kind === "boolean") {
    value = correctionValue.value.trim().toLowerCase() === "true";
  }
  const path = `line_items.${props.lineIndex}.${selectedField.value}`;
  emit("saveCorrection", {
    fieldPath: path,
    value,
    lineIndex: props.lineIndex,
  });
}

function editableValue(item: LineItem, path: string): string {
  const value = path.split(".").reduce<unknown>((current, segment) => (
    current && typeof current === "object" ? (current as Record<string, unknown>)[segment] : undefined
  ), item);
  if (value == null) return "";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}
</script>

<template>
  <div>
    <!-- Mobile & Desktop Backdrop -->
    <div
      v-if="isOpen && lineItem"
      class="fixed inset-0 z-40 bg-slate-900/40 backdrop-blur-xs transition-opacity"
      @click="emit('close')"
    ></div>

    <!-- Product Drawer -->
    <aside
      v-if="isOpen && lineItem"
      class="fixed inset-y-0 right-0 z-50 flex h-full w-full sm:max-w-xl md:max-w-2xl flex-col border-l border-rule bg-surface shadow-2xl transition-transform"
      aria-labelledby="product-drawer-title"
    >
      <!-- Drawer Header -->
      <div class="flex items-center justify-between border-b border-rule px-4 py-3 sm:px-6 sm:py-4 bg-surface-alt/60">
        <div class="min-w-0 flex-1 pr-2">
          <div class="flex flex-wrap items-center gap-2">
            <span class="rounded-md bg-axmed-primary-tint px-2 py-0.5 text-[11px] font-bold text-axmed-primary border border-rule">
              Line {{ lineIndex + 1 }}
            </span>
            <span class="relative text-xs font-semibold text-ink-3" data-tooltip-container>
              <button
                type="button"
                class="cursor-help rounded px-1 text-left hover:bg-surface transition cursor-pointer"
                :aria-expanded="showMappingExplanation"
                aria-label="Explain mapping confidence"
                @click.stop="showMappingExplanation = !showMappingExplanation"
              >
                Mapping confidence: <strong class="text-axmed-primary">{{ rowMappingConfidence != null ? `${rowMappingConfidence}%` : (rowMappingIssueCount === 0 ? "No issues" : "Needs review") }}</strong>
              </button>
              <span
                v-if="showMappingExplanation"
                role="tooltip"
                class="absolute left-0 sm:right-0 sm:left-auto top-7 z-50 w-72 rounded-lg border border-rule bg-surface p-3 text-[11px] font-normal leading-4 text-ink-2 shadow-lg"
              >
                {{ rowMappingExplanation }}
              </span>
            </span>
          </div>
          <h2 id="product-drawer-title" class="mt-1 text-base sm:text-lg font-bold text-ink truncate">
            {{ lineItem.product.trade_name || "Product Details" }}
          </h2>
        </div>
        <button
          type="button"
          class="rounded-lg p-2 text-ink-3 hover:bg-surface-alt hover:text-ink transition cursor-pointer shrink-0"
          aria-label="Close product details"
          @click="emit('close')"
        >
          ✕
        </button>
      </div>

      <!-- Drawer Body (Scrollable) -->
      <div class="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4 sm:space-y-6 text-xs">
        <div v-if="extractionFactors.length" class="rounded-2xl border border-sky-200 bg-sky-50/50 p-4">
          <div class="flex items-center justify-between gap-3">
            <h3 class="text-xs font-bold uppercase tracking-wider text-sky-900">Extraction confidence</h3>
            <span class="relative" data-tooltip-container>
              <button
                type="button"
                class="flex h-5 w-5 items-center justify-center rounded-full border border-sky-300 text-[10px] font-bold text-sky-700 hover:bg-sky-100"
                aria-label="How extraction confidence is calculated"
                :aria-expanded="showExtractionCalculation"
                @click.stop="showExtractionCalculation = !showExtractionCalculation"
              >
                ?
              </button>
              <span
                v-if="showExtractionCalculation"
                role="tooltip"
                class="absolute right-0 top-7 z-50 w-80 rounded-lg border border-slate-200 bg-white p-3 text-[11px] font-normal leading-4 text-slate-700 shadow-lg"
              >
                <span class="font-semibold text-slate-900">How this is calculated</span>
                <span class="mt-1 block">The score combines readability, parser quality, recovered evidence, OCR quality, and agreement between independent OCR and vision readings. Only observed recovery problems reduce the score.</span>
                <span class="mt-2 block whitespace-pre-line">{{ extractionCalculation }}</span>
              </span>
            </span>
          </div>
          <p class="mt-1 text-[11px] text-sky-800">
            {{ document.extraction_confidence?.score }}% · {{ extractionSummary }} Mapping is assessed separately.
          </p>
          <span class="sr-only">{{ extractionCalculation }}</span>
        </div>

        <div v-if="showMappingConcernDefinition" role="tooltip" class="rounded-xl border border-amber-200 bg-amber-50 p-3 text-[11px] leading-4 text-amber-900" data-tooltip-container>
          <div class="flex items-start justify-between gap-2">
            <div>
              <span class="font-semibold">How field mapping confidence is calculated:</span>
              {{ mappingConcernDefinition }}
            </div>
            <button type="button" class="text-amber-700 hover:text-amber-900 font-bold text-xs" @click.stop="showMappingConcernDefinition = false">✕</button>
          </div>
        </div>

        <!-- Edit / Correction Card (Clean & Inline) -->
        <div class="rounded-2xl border border-axmed-primary/20 bg-axmed-primary-tint/60 p-4 shadow-xs">
          <div class="flex items-center justify-between">
            <h3 class="text-xs font-bold uppercase tracking-wider text-axmed-primary">
              Edit Product Fields
            </h3>
            <span class="text-[11px] text-axmed-primary font-semibold">Editable review correction</span>
          </div>
          <p class="mt-1 text-[11px] text-ink-2">
            Every source-provided field in this product can be corrected here. Changes recalculate commercial terms automatically.
          </p>

          <div class="mt-3 grid grid-cols-1 sm:grid-cols-[160px_1fr_auto] gap-2 items-center">
            <select
              v-model="selectedField"
              class="rounded-xl border border-rule-dark bg-surface px-3 py-2 text-xs font-medium text-ink focus:border-axmed-primary focus:outline-none"
              aria-label="Correction field"
            >
              <option v-for="field in editableFields" :key="field.path" :value="field.path">
                {{ field.label }}
              </option>
            </select>

            <input
              v-model="correctionValue"
              class="rounded-xl border border-rule-dark bg-surface px-3 py-2 text-xs text-ink focus:border-axmed-primary focus:outline-none placeholder:text-ink-3"
              :aria-label="`Correction value for ${lineItem.product.trade_name ?? lineIndex}`"
              :placeholder="editableFields.find((field) => field.path === selectedField)?.kind === 'json' ? 'Enter valid JSON' : 'Enter corrected value'"
              @keydown.enter="handleSave"
            />

            <button
              type="button"
              class="rounded-xl bg-[#261c7a] px-4 py-2 text-xs font-bold text-white hover:bg-[#1e155c] active:bg-[#150f42] transition disabled:opacity-50 whitespace-nowrap cursor-pointer shadow-xs"
              :disabled="busy || !correctionValue.trim()"
              @click="handleSave"
            >
              {{ busy ? "Saving…" : "Save correction" }}
            </button>
          </div>
        </div>

        <!-- Section 1: Product Identity -->
        <div class="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
          <h3 class="text-xs font-bold uppercase tracking-wider text-slate-400 border-b border-slate-100 pb-2 mb-3">
            Product Identity
          </h3>
          <div v-if="mappingIssuesFor('product').length" class="mb-3 rounded-lg border border-rose-200 bg-rose-50 p-2 text-[11px] text-rose-800">
            <p v-for="issue in mappingIssuesFor('product')" :key="`${issue.field_path}:${issue.code}`">{{ issue.message }}</p>
          </div>
          <div v-if="mappingConcernsFor('product').length" class="mb-3 rounded-lg border border-amber-200 bg-amber-50 p-2 text-[11px] text-amber-900">
            <p class="flex items-center gap-1 font-semibold">
              {{ mappingConcernsFor('product').length }} field{{ mappingConcernsFor('product').length === 1 ? "" : "s" }} below full mapping confidence:
              <button type="button" data-tooltip-container class="flex h-4 w-4 items-center justify-center rounded-full border border-amber-500 text-[9px] font-bold hover:bg-amber-100" aria-label="Explain field mapping confidence" :aria-expanded="showMappingConcernDefinition" @click.stop="showMappingConcernDefinition = !showMappingConcernDefinition">?</button>
            </p>
            <p v-for="concern in mappingConcernsFor('product')" :key="concern.label">{{ concern.label }} ({{ concern.score }}%): {{ concern.reason }}</p>
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <span class="text-[10px] font-bold uppercase text-slate-400">Trade Name</span>
              <p class="font-bold text-slate-800">{{ lineItem.product.trade_name || "—" }}</p>
            </div>
            <div>
              <span class="text-[10px] font-bold uppercase text-slate-400">Active Ingredients (INN)</span>
              <p class="font-medium text-slate-800">{{ lineItem.product.inn.join(" · ") || "—" }}</p>
            </div>
            <div>
              <span class="text-[10px] font-bold uppercase text-slate-400">Strength</span>
              <p class="font-medium text-slate-800">
                {{ (lineItem.product.strength ?? []).map((s) => `${displayValue(s.value)} ${displayValue(s.unit)}${s.per_value ? ` / ${s.per_value} ${s.per_unit}` : ""}`).join(" · ") || "—" }}
              </p>
            </div>
            <div>
              <span class="text-[10px] font-bold uppercase text-slate-400">Dosage Form</span>
              <p class="font-medium text-slate-800">{{ lineItem.product.dosage_form || "—" }}</p>
            </div>
            <div>
              <span class="text-[10px] font-bold uppercase text-slate-400">Manufacturer</span>
              <p class="font-medium text-slate-800">{{ lineItem.product.manufacturer || "—" }}</p>
            </div>
            <div>
              <span class="text-[10px] font-bold uppercase text-slate-400">Country of Origin</span>
              <p class="font-medium text-slate-800">{{ lineItem.product.country_of_origin || "—" }}</p>
            </div>
          </div>
        </div>

        <!-- Section 2: Pricing & Commercial Terms -->
        <div class="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
          <h3 class="text-xs font-bold uppercase tracking-wider text-slate-400 border-b border-slate-100 pb-2 mb-3">
            Pricing & Commercial Terms
          </h3>
          <div v-if="mappingIssuesFor('pricing').length" class="mb-3 rounded-lg border border-rose-200 bg-rose-50 p-2 text-[11px] text-rose-800">
            <p v-for="issue in mappingIssuesFor('pricing')" :key="`${issue.field_path}:${issue.code}`">{{ issue.message }}</p>
          </div>
          <div v-if="mappingConcernsFor('pricing').length" class="mb-3 rounded-lg border border-amber-200 bg-amber-50 p-2 text-[11px] text-amber-900">
            <p class="flex items-center gap-1 font-semibold">
              {{ mappingConcernsFor('pricing').length }} field{{ mappingConcernsFor('pricing').length === 1 ? "" : "s" }} below full mapping confidence:
              <button type="button" data-tooltip-container class="flex h-4 w-4 items-center justify-center rounded-full border border-amber-500 text-[9px] font-bold hover:bg-amber-100" aria-label="Explain field mapping confidence" :aria-expanded="showMappingConcernDefinition" @click.stop="showMappingConcernDefinition = !showMappingConcernDefinition">?</button>
            </p>
            <p v-for="concern in mappingConcernsFor('pricing')" :key="concern.label">{{ concern.label }} ({{ concern.score }}%): {{ concern.reason }}</p>
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <span class="text-[10px] font-bold uppercase text-slate-400">Quoted Price</span>
              <p class="font-bold text-slate-800">
                {{ lineItem.pricing.currency }} {{ displayPrice(lineItem.pricing.quoted_price.amount) }} / {{ lineItem.pricing.quoted_price.uom || "unit" }}
              </p>
            </div>
            <div>
              <span class="text-[10px] font-bold uppercase text-slate-400">Pack Price</span>
              <p class="font-medium text-slate-800">
                {{ lineItem.pricing.pack_price ? `${lineItem.pricing.currency} ${displayPrice(lineItem.pricing.pack_price)}` : "—" }}
              </p>
            </div>
            <div>
              <span class="text-[10px] font-bold uppercase text-slate-400">Normalized Price</span>
              <p class="font-bold text-emerald-700">
                {{ lineItem.pricing.currency }} {{ displayPrice(lineItem.pricing.normalized_price?.amount, lineItem.pricing.quoted_price?.amount) }} / {{ lineItem.pricing.normalized_price?.uom || "unit" }}
              </p>
              <span v-if="lineItem.pricing.normalized_price?.calculation" class="text-[10px] text-slate-400">
                Formula: {{ lineItem.pricing.normalized_price.calculation }}
              </span>
              <span v-if="lineItem.pricing.normalized_price?.derived" class="mt-1 block text-[10px] font-semibold text-slate-500">
                Derived value<span v-if="lineItem.pricing.normalized_price?.validation_status"> · Validation {{ lineItem.pricing.normalized_price.validation_status }}</span>
              </span>
            </div>
            <div>
              <span class="text-[10px] font-bold uppercase text-slate-400">Discount & Extended Price</span>
              <p class="font-medium text-slate-800">
                {{ lineItem.pricing.discount ? `${lineItem.pricing.discount}%` : "No discount" }}
                <span v-if="lineItem.pricing.extended_price">
                  · Total {{ lineItem.pricing.currency }} {{ displayPrice(lineItem.pricing.extended_price) }}
                </span>
              </p>
            </div>
          </div>

          <!-- Price Tiers if available -->
          <div v-if="lineItem.pricing.price_tiers?.length" class="mt-3 pt-3 border-t border-slate-100">
            <div class="flex items-center justify-between mb-1">
              <span class="text-[10px] font-bold uppercase text-slate-400">Volume Price Tiers</span>
              <span class="text-[10px] font-semibold text-slate-500">{{ lineItem.pricing.price_tiers.length }} price tiers</span>
            </div>
            <div class="space-y-1">
              <div
                v-for="(tier, idx) in lineItem.pricing.price_tiers"
                :key="idx"
                class="flex justify-between rounded-lg bg-slate-50 p-2 text-[11px]"
              >
                <span>≥ {{ displayValue(tier.min_quantity) }} {{ tier.quantity_uom || "" }}</span>
                <span class="font-bold">{{ lineItem.pricing.currency }} {{ displayPrice(tier.price) }} / {{ tier.price_uom || "unit" }}</span>
              </div>
            </div>
          </div>

          <!-- Adjustments if available -->
          <div v-if="lineItem.pricing.adjustments?.length" class="mt-3 pt-3 border-t border-slate-100">
            <div class="flex items-center justify-between mb-1">
              <span class="text-[10px] font-bold uppercase text-slate-400">Commercial Adjustments</span>
              <span class="text-[10px] font-semibold text-slate-500">{{ lineItem.pricing.adjustments.length }} adjustments</span>
            </div>
            <div class="space-y-1">
              <div
                v-for="(adj, idx) in lineItem.pricing.adjustments"
                :key="idx"
                class="flex justify-between rounded-lg bg-slate-50 p-2 text-[11px]"
              >
                <span class="capitalize">{{ adj.type }}</span>
                <span class="font-bold">{{ adj.value ? `${adj.value}${adj.value_type === 'percentage' ? '%' : ''}` : '—' }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Section 3: Quantity & Packaging -->
        <div class="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
          <h3 class="text-xs font-bold uppercase tracking-wider text-slate-400 border-b border-slate-100 pb-2 mb-3">
            Quantity & Packaging
          </h3>
          <div v-if="mappingIssuesFor('quantity_packaging').length" class="mb-3 rounded-lg border border-rose-200 bg-rose-50 p-2 text-[11px] text-rose-800">
            <p v-for="issue in mappingIssuesFor('quantity_packaging')" :key="`${issue.field_path}:${issue.code}`">{{ issue.message }}</p>
          </div>
          <div v-if="mappingConcernsFor('quantity_packaging').length" class="mb-3 rounded-lg border border-amber-200 bg-amber-50 p-2 text-[11px] text-amber-900">
            <p class="flex items-center gap-1 font-semibold">
              {{ mappingConcernsFor('quantity_packaging').length }} field{{ mappingConcernsFor('quantity_packaging').length === 1 ? "" : "s" }} below full mapping confidence:
              <button type="button" data-tooltip-container class="flex h-4 w-4 items-center justify-center rounded-full border border-amber-500 text-[9px] font-bold hover:bg-amber-100" aria-label="Explain field mapping confidence" :aria-expanded="showMappingConcernDefinition" @click.stop="showMappingConcernDefinition = !showMappingConcernDefinition">?</button>
            </p>
            <p v-for="concern in mappingConcernsFor('quantity_packaging')" :key="concern.label">{{ concern.label }} ({{ concern.score }}%): {{ concern.reason }}</p>
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <span class="text-[10px] font-bold uppercase text-slate-400">Quoted Quantity</span>
              <p class="font-bold text-slate-800">
                {{ displayValue(lineItem.quantity.quoted_quantity) }} {{ lineItem.quantity.quoted_quantity_uom || "" }}
              </p>
            </div>
            <div>
              <span class="text-[10px] font-bold uppercase text-slate-400">Minimum Order Qty (MOQ)</span>
              <p class="font-medium text-slate-800">
                {{ displayValue(lineItem.quantity.minimum_order_quantity) }} {{ lineItem.quantity.minimum_order_quantity_uom || "" }}
              </p>
            </div>
            <div>
              <span class="text-[10px] font-bold uppercase text-slate-400">Primary Pack</span>
              <p class="font-medium text-slate-800">{{ lineItem.packaging.primary_pack || "—" }}</p>
            </div>
            <div>
              <span class="text-[10px] font-bold uppercase text-slate-400">Units Per Pack</span>
              <p class="font-medium text-slate-800">
                {{ lineItem.packaging.units_per_pack ? `${lineItem.packaging.units_per_pack} ${lineItem.packaging.unit_label || "units"}` : "—" }}
              </p>
            </div>
            <div>
              <span class="text-[10px] font-bold uppercase text-slate-400">Packs Per Shipper</span>
              <p class="font-medium text-slate-800">
                {{ lineItem.packaging.packs_per_shipper ? `${lineItem.packaging.packs_per_shipper} packs / shipper` : "—" }}
              </p>
            </div>
            <div>
              <span class="text-[10px] font-bold uppercase text-slate-400">Presentation</span>
              <p class="font-medium text-slate-800">{{ lineItem.packaging.presentation || "—" }}</p>
            </div>
          </div>
        </div>

        <!-- Section 4: Supply & Logistics -->
        <div class="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
          <h3 class="text-xs font-bold uppercase tracking-wider text-slate-400 border-b border-slate-100 pb-2 mb-3">
            Supply & Logistics
          </h3>
          <div v-if="mappingIssuesFor('supply').length" class="mb-3 rounded-lg border border-rose-200 bg-rose-50 p-2 text-[11px] text-rose-800">
            <p v-for="issue in mappingIssuesFor('supply')" :key="`${issue.field_path}:${issue.code}`">{{ issue.message }}</p>
          </div>
          <div v-if="mappingConcernsFor('supply').length" class="mb-3 rounded-lg border border-amber-200 bg-amber-50 p-2 text-[11px] text-amber-900">
            <p class="flex items-center gap-1 font-semibold">
              {{ mappingConcernsFor('supply').length }} field{{ mappingConcernsFor('supply').length === 1 ? "" : "s" }} below full mapping confidence:
              <button type="button" data-tooltip-container class="flex h-4 w-4 items-center justify-center rounded-full border border-amber-500 text-[9px] font-bold hover:bg-amber-100" aria-label="Explain field mapping confidence" :aria-expanded="showMappingConcernDefinition" @click.stop="showMappingConcernDefinition = !showMappingConcernDefinition">?</button>
            </p>
            <p v-for="concern in mappingConcernsFor('supply')" :key="concern.label">{{ concern.label }} ({{ concern.score }}%): {{ concern.reason }}</p>
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <span class="text-[10px] font-bold uppercase text-slate-400">Lead Time</span>
              <p class="font-medium text-slate-800">
                {{ displayLeadTime(lineItem.supply) }}
              </p>
            </div>
            <div>
              <span class="text-[10px] font-bold uppercase text-slate-400">Shipping Transit</span>
              <p class="font-medium text-slate-800">
                {{ displayTransitDuration }}
              </p>
            </div>
            <div>
              <span class="text-[10px] font-bold uppercase text-slate-400">Shelf Life</span>
              <p class="font-medium text-slate-800">
                {{ lineItem.supply.shelf_life_months ? `${lineItem.supply.shelf_life_months} months` : "—" }}
                <span v-if="lineItem.supply.minimum_remaining_shelf_life_percent">
                  (min {{ lineItem.supply.minimum_remaining_shelf_life_percent }}% remaining)
                </span>
              </p>
            </div>
            <div>
              <span class="text-[10px] font-bold uppercase text-slate-400">Cold Chain</span>
              <p class="font-medium text-slate-800">
                {{ lineItem.supply.cold_chain_required != null ? (lineItem.supply.cold_chain_required ? "Required" : "Not required") : "—" }}
              </p>
            </div>
            <div class="sm:col-span-2">
              <span class="text-[10px] font-bold uppercase text-slate-400">Storage Conditions</span>
              <p class="font-medium text-slate-800">{{ lineItem.supply.storage_conditions || "—" }}</p>
            </div>
          </div>
        </div>

        <!-- Section 5: Regulatory & Compliance -->
        <div class="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
          <h3 class="text-xs font-bold uppercase tracking-wider text-slate-400 border-b border-slate-100 pb-2 mb-3">
            Regulatory & Compliance
          </h3>
          <div v-if="mappingIssuesFor('regulatory').length" class="mb-3 rounded-lg border border-rose-200 bg-rose-50 p-2 text-[11px] text-rose-800">
            <p v-for="issue in mappingIssuesFor('regulatory')" :key="`${issue.field_path}:${issue.code}`">{{ issue.message }}</p>
          </div>
          <div v-if="mappingConcernsFor('regulatory').length" class="mb-3 rounded-lg border border-amber-200 bg-amber-50 p-2 text-[11px] text-amber-900">
            <p class="flex items-center gap-1 font-semibold">
              {{ mappingConcernsFor('regulatory').length }} field{{ mappingConcernsFor('regulatory').length === 1 ? "" : "s" }} below full mapping confidence:
              <button type="button" data-tooltip-container class="flex h-4 w-4 items-center justify-center rounded-full border border-amber-500 text-[9px] font-bold hover:bg-amber-100" aria-label="Explain field mapping confidence" :aria-expanded="showMappingConcernDefinition" @click.stop="showMappingConcernDefinition = !showMappingConcernDefinition">?</button>
            </p>
            <p v-for="concern in mappingConcernsFor('regulatory')" :key="concern.label">{{ concern.label }} ({{ concern.score }}%): {{ concern.reason }}</p>
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <span class="text-[10px] font-bold uppercase text-slate-400">WHO Prequalified</span>
              <p class="font-medium text-slate-800">
                <span v-if="lineItem.regulatory?.who_prequalified != null">
                  {{ lineItem.regulatory.who_prequalified ? `WHO prequalified${lineItem.regulatory.who_pq_reference ? ` · ${lineItem.regulatory.who_pq_reference}` : ""}` : "WHO not prequalified" }}
                </span>
                <span v-else>—</span>
              </p>
            </div>
            <div>
              <span class="text-[10px] font-bold uppercase text-slate-400">Registered Markets</span>
              <p class="font-medium text-slate-800">
                {{ lineItem.regulatory?.registered_markets?.length ? `markets: ${lineItem.regulatory.registered_markets.join(", ")}` : "—" }}
              </p>
            </div>
            <div>
              <span class="text-[10px] font-bold uppercase text-slate-400">Regulatory Status</span>
              <p class="font-medium text-slate-800">{{ lineItem.regulatory?.regulatory_status || "—" }}</p>
            </div>
          </div>
        </div>
      </div>
    </aside>
  </div>
</template>
