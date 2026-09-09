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

const displayCurrency = computed(
  () => props.lineItem?.pricing.currency || props.document.quotation?.commercial_terms.currency || "",
);

function closeTooltips() {
  showExtractionCalculation.value = false;
  showMappingExplanation.value = false;
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
  if (!scores.length) return "Mapping confidence is unavailable for this line item.";
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

function issuesForField(fieldOrFields: string | string[]) {
  const prefix = `line_items[${props.lineIndex}].`;
  const targets = Array.isArray(fieldOrFields) ? fieldOrFields : [fieldOrFields];
  return (props.document.mapping_issues ?? []).filter((issue) => {
    if (issue.field_path.startsWith("commercial_terms.")) {
      return targets.some((t) => t.startsWith("commercial_terms.") && (issue.field_path === t || issue.field_path.startsWith(`${t}.`) || issue.field_path.startsWith(`${t}_`)));
    }
    if (!issue.field_path.startsWith(prefix)) return false;
    const subPath = issue.field_path.slice(prefix.length);
    return targets.some(
      (target) =>
        subPath === target ||
        subPath.startsWith(`${target}.`) ||
        subPath.startsWith(`${target}_`) ||
        subPath.startsWith(`${target}[`) ||
        target.startsWith(`${subPath}.`)
    );
  });
}

function mappingIssueText(issue: { field_path: string; message: string }) {
  const fieldPath = issue.field_path.replace(/^line_items\[\d+\]\.(product|pricing|quantity|packaging|supply|regulatory)\./, "");
  const strengthMatch = fieldPath.match(/^strength\[(\d+)\](?:\.(.+))?$/);
  if (strengthMatch) {
    const sIndex = Number(strengthMatch[1]);
    const subField = strengthMatch[2];
    const strengthObj = props.lineItem?.product?.strength?.[sIndex];
    if (strengthObj) {
      const parts: string[] = [];
      if (strengthObj.ingredient) {
        parts.push(strengthObj.ingredient);
      }
      parts.push("strength");
      if (strengthObj.value != null) parts.push(String(strengthObj.value));
      if (strengthObj.unit) parts.push(strengthObj.unit);
      if (strengthObj.per_value != null || strengthObj.per_unit) {
        const perParts = [strengthObj.per_value, strengthObj.per_unit].filter((p) => p != null && p !== "");
        if (perParts.length) parts.push(`/ ${perParts.join(" ")}`);
      }
      let strengthLabel = parts.join(" ");
      if (!strengthObj.ingredient && subField) {
        strengthLabel = `Strength ${sIndex + 1}`;
      }
      if (subField) {
        const subLabel = subField.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
        strengthLabel = `${strengthLabel} · ${subLabel}`;
      }
      const [, reason = issue.message] = issue.message.split("; ", 2);
      return `${strengthLabel} — ${reason}`;
    }
  }

  const recordMatch = issue.message.match(/^Record source evidence for (.+?); (.+)$/);
  if (recordMatch && (recordMatch[1].includes(" ") || recordMatch[1].includes("("))) {
    return `${recordMatch[1]} — ${recordMatch[2]}`;
  }
  const confirmMatch = issue.message.match(/^Confirm (.+?); (.+)$/);
  if (confirmMatch && (confirmMatch[1].includes(" ") || confirmMatch[1].includes("("))) {
    return `${confirmMatch[1]} — ${confirmMatch[2]}`;
  }

  const context = fieldPath.split(".").map((segment) => {
    const match = segment.match(/^(.+?)(?:\[(\d+)\])?$/);
    const label = (match?.[1] ?? segment).replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
    return match?.[2] == null ? label : `${label} ${Number(match[2]) + 1}`;
  }).join(" · ");
  const [, reason = issue.message] = issue.message.split("; ", 2);
  return `${context} — ${reason}`;
}

const hasStrengthIssue = computed(() =>
  issuesForField("product.strength").length > 0
);

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
            <span class="rounded-md border border-rule bg-white px-2 py-0.5 text-[11px] font-semibold text-ink-2">
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
                Mapping confidence: <strong class="text-ink">{{ rowMappingConfidence != null ? `${rowMappingConfidence}%` : "—" }}</strong>
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
        <div v-if="extractionFactors.length" class="rounded-xl border border-rule bg-surface-alt/60 p-4">
          <div class="flex items-center justify-between gap-3">
            <h3 class="text-[10px] font-bold uppercase tracking-wider text-ink-2">Extraction confidence</h3>
            <span class="relative" data-tooltip-container>
              <button
                type="button"
                class="flex h-5 w-5 items-center justify-center rounded-full border border-rule-dark text-[10px] font-bold text-ink-3 hover:bg-white hover:text-ink"
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
          <p class="mt-1 text-[11px] leading-4 text-ink-2">
            {{ document.extraction_confidence?.score }}% · {{ extractionSummary }} Mapping is assessed separately.
          </p>
          <span class="sr-only">{{ extractionCalculation }}</span>
        </div>

        <!-- Edit / Correction Card (Clean & Inline) -->
        <div class="rounded-xl border border-rule bg-white p-4 shadow-xs">
          <div class="flex items-center justify-between">
            <h3 class="text-[10px] font-bold uppercase tracking-wider text-ink-2">
              Edit Product Fields
            </h3>
            <span class="text-[11px] text-ink-3">Editable fields</span>
          </div>
          <p class="mt-1 text-[11px] text-ink-2">
            Every source-provided field in this product can be corrected here. Changes recalculate commercial terms automatically.
          </p>

          <div class="mt-3 grid grid-cols-1 sm:grid-cols-[160px_1fr_auto] gap-2 items-center">
            <select
              v-model="selectedField"
              class="app-select w-full text-xs"
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
          <details v-if="mappingIssuesFor('product').length" class="mb-3 border-l-2 border-amber-500 bg-surface-alt px-3 py-2 text-[11px] text-ink-2">
            <summary class="flex cursor-pointer items-center justify-between gap-3 font-semibold marker:text-amber-600">
              <span>{{ mappingIssuesFor('product').length }} mapping {{ mappingIssuesFor('product').length === 1 ? "issue" : "issues" }}</span>
              <span class="text-[10px] font-medium text-ink-3">View details</span>
            </summary>
            <div class="mt-2 space-y-1 border-t border-amber-200 pt-2">
              <p v-for="issue in mappingIssuesFor('product')" :key="`${issue.field_path}:${issue.code}`">{{ mappingIssueText(issue) }}</p>
            </div>
          </details>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <div class="flex items-center gap-1.5">
                <span class="text-[10px] font-bold uppercase text-slate-400">Trade Name</span>
                <span
                  v-if="issuesForField('product.trade_name').length"
                  class="rounded bg-amber-100 px-1.5 py-0.5 text-[9px] font-semibold text-amber-800"
                >
                  Mapping issue
                </span>
              </div>
              <p class="font-bold text-slate-800">{{ lineItem.product.trade_name || "—" }}</p>
              <p
                v-for="issue in issuesForField('product.trade_name')"
                :key="`${issue.field_path}:${issue.code}`"
                class="mt-1 text-[11px] text-amber-700"
              >
                ⚠ {{ mappingIssueText(issue) }}
              </p>
            </div>
            <div>
              <div class="flex items-center gap-1.5">
                <span class="text-[10px] font-bold uppercase text-slate-400">Active Ingredients (INN)</span>
                <span
                  v-if="issuesForField('product.inn').length"
                  class="rounded bg-amber-100 px-1.5 py-0.5 text-[9px] font-semibold text-amber-800"
                >
                  Mapping issue
                </span>
              </div>
              <p class="font-medium text-slate-800">{{ lineItem.product.inn.join(" · ") || "—" }}</p>
              <p
                v-for="issue in issuesForField('product.inn')"
                :key="`${issue.field_path}:${issue.code}`"
                class="mt-1 text-[11px] text-amber-700"
              >
                ⚠ {{ mappingIssueText(issue) }}
              </p>
            </div>
            <div>
              <div class="flex items-center gap-1.5">
                <span class="text-[10px] font-bold uppercase text-slate-400">Strength</span>
                <span
                  v-if="hasStrengthIssue"
                  class="rounded bg-amber-100 px-1.5 py-0.5 text-[9px] font-semibold text-amber-800"
                  title="Mapping issue detected for strength"
                >
                  Mapping issue
                </span>
              </div>
              <p class="font-medium text-slate-800">
                {{ (lineItem.product.strength ?? []).map((s) => `${displayValue(s.value)} ${displayValue(s.unit)}${s.per_value ? ` / ${s.per_value} ${s.per_unit}` : ""}`).join(" · ") || "—" }}
              </p>
              <p
                v-for="issue in issuesForField('product.strength')"
                :key="`${issue.field_path}:${issue.code}`"
                class="mt-1 text-[11px] text-amber-700"
              >
                ⚠ {{ mappingIssueText(issue) }}
              </p>
            </div>
            <div>
              <div class="flex items-center gap-1.5">
                <span class="text-[10px] font-bold uppercase text-slate-400">Dosage Form</span>
                <span
                  v-if="issuesForField('product.dosage_form').length"
                  class="rounded bg-amber-100 px-1.5 py-0.5 text-[9px] font-semibold text-amber-800"
                >
                  Mapping issue
                </span>
              </div>
              <p class="font-medium text-slate-800">{{ lineItem.product.dosage_form || "—" }}</p>
              <p
                v-for="issue in issuesForField('product.dosage_form')"
                :key="`${issue.field_path}:${issue.code}`"
                class="mt-1 text-[11px] text-amber-700"
              >
                ⚠ {{ mappingIssueText(issue) }}
              </p>
            </div>
            <div>
              <div class="flex items-center gap-1.5">
                <span class="text-[10px] font-bold uppercase text-slate-400">Manufacturer</span>
                <span
                  v-if="issuesForField('product.manufacturer').length"
                  class="rounded bg-amber-100 px-1.5 py-0.5 text-[9px] font-semibold text-amber-800"
                >
                  Mapping issue
                </span>
              </div>
              <p class="font-medium text-slate-800">{{ lineItem.product.manufacturer || "—" }}</p>
              <p
                v-for="issue in issuesForField('product.manufacturer')"
                :key="`${issue.field_path}:${issue.code}`"
                class="mt-1 text-[11px] text-amber-700"
              >
                ⚠ {{ mappingIssueText(issue) }}
              </p>
            </div>
            <div>
              <div class="flex items-center gap-1.5">
                <span class="text-[10px] font-bold uppercase text-slate-400">Country of Origin</span>
                <span
                  v-if="issuesForField('product.country_of_origin').length"
                  class="rounded bg-amber-100 px-1.5 py-0.5 text-[9px] font-semibold text-amber-800"
                >
                  Mapping issue
                </span>
              </div>
              <p class="font-medium text-slate-800">{{ lineItem.product.country_of_origin || "—" }}</p>
              <p
                v-for="issue in issuesForField('product.country_of_origin')"
                :key="`${issue.field_path}:${issue.code}`"
                class="mt-1 text-[11px] text-amber-700"
              >
                ⚠ {{ mappingIssueText(issue) }}
              </p>
            </div>
          </div>
        </div>

        <!-- Section 2: Pricing & Commercial Terms -->
        <div class="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
          <h3 class="text-xs font-bold uppercase tracking-wider text-slate-400 border-b border-slate-100 pb-2 mb-3">
            Pricing & Commercial Terms
          </h3>
          <details v-if="mappingIssuesFor('pricing').length" class="mb-3 border-l-2 border-amber-500 bg-surface-alt px-3 py-2 text-[11px] text-ink-2">
            <summary class="flex cursor-pointer items-center justify-between gap-3 font-semibold marker:text-amber-600">
              <span>{{ mappingIssuesFor('pricing').length }} mapping {{ mappingIssuesFor('pricing').length === 1 ? "issue" : "issues" }}</span>
              <span class="text-[10px] font-medium text-ink-3">View details</span>
            </summary>
            <div class="mt-2 space-y-1 border-t border-amber-200 pt-2">
              <p v-for="issue in mappingIssuesFor('pricing')" :key="`${issue.field_path}:${issue.code}`">{{ mappingIssueText(issue) }}</p>
            </div>
          </details>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <div class="flex items-center gap-1.5">
                <span class="text-[10px] font-bold uppercase text-slate-400">Quoted Price</span>
                <span
                  v-if="issuesForField(['pricing.quoted_price', 'pricing.currency']).length"
                  class="rounded bg-amber-100 px-1.5 py-0.5 text-[9px] font-semibold text-amber-800"
                >
                  Mapping issue
                </span>
              </div>
              <p class="font-bold text-slate-800">
                {{ displayCurrency }} {{ displayPrice(lineItem.pricing.quoted_price.amount) }} / {{ lineItem.pricing.quoted_price.uom || "unit" }}
              </p>
              <p
                v-for="issue in issuesForField(['pricing.quoted_price', 'pricing.currency'])"
                :key="`${issue.field_path}:${issue.code}`"
                class="mt-1 text-[11px] text-amber-700"
              >
                ⚠ {{ mappingIssueText(issue) }}
              </p>
            </div>
            <div>
              <div class="flex items-center gap-1.5">
                <span class="text-[10px] font-bold uppercase text-slate-400">Pack Price</span>
                <span
                  v-if="issuesForField('pricing.pack_price').length"
                  class="rounded bg-amber-100 px-1.5 py-0.5 text-[9px] font-semibold text-amber-800"
                >
                  Mapping issue
                </span>
              </div>
              <p class="font-medium text-slate-800">
                {{ lineItem.pricing.pack_price ? `${displayCurrency} ${displayPrice(lineItem.pricing.pack_price)}` : "—" }}
              </p>
              <p
                v-for="issue in issuesForField('pricing.pack_price')"
                :key="`${issue.field_path}:${issue.code}`"
                class="mt-1 text-[11px] text-amber-700"
              >
                ⚠ {{ mappingIssueText(issue) }}
              </p>
            </div>
            <div>
              <div class="flex items-center gap-1.5">
                <span class="text-[10px] font-bold uppercase text-slate-400">Normalized Price</span>
                <span
                  v-if="issuesForField('pricing.normalized_price').length"
                  class="rounded bg-amber-100 px-1.5 py-0.5 text-[9px] font-semibold text-amber-800"
                >
                  Mapping issue
                </span>
              </div>
              <p class="font-bold text-slate-800">
                {{ displayCurrency }} {{ displayPrice(lineItem.pricing.normalized_price?.amount, lineItem.pricing.quoted_price?.amount) }} / {{ lineItem.pricing.normalized_price?.uom || "unit" }}
              </p>
              <span v-if="lineItem.pricing.normalized_price?.calculation" class="text-[10px] text-slate-400">
                Formula: {{ lineItem.pricing.normalized_price.calculation }}
              </span>
              <span v-if="lineItem.pricing.normalized_price?.derived" class="mt-1 block text-[10px] font-semibold text-slate-500">
                Derived value<span v-if="lineItem.pricing.normalized_price?.validation_status"> · Validation {{ lineItem.pricing.normalized_price.validation_status }}</span>
              </span>
              <p
                v-for="issue in issuesForField('pricing.normalized_price')"
                :key="`${issue.field_path}:${issue.code}`"
                class="mt-1 text-[11px] text-amber-700"
              >
                ⚠ {{ mappingIssueText(issue) }}
              </p>
            </div>
            <div>
              <div class="flex items-center gap-1.5">
                <span class="text-[10px] font-bold uppercase text-slate-400">Discount & Extended Price</span>
                <span
                  v-if="issuesForField(['pricing.discount', 'pricing.extended_price']).length"
                  class="rounded bg-amber-100 px-1.5 py-0.5 text-[9px] font-semibold text-amber-800"
                >
                  Mapping issue
                </span>
              </div>
              <p class="font-medium text-slate-800">
                {{ lineItem.pricing.discount ? `${lineItem.pricing.discount}%` : "No discount" }}
                <span v-if="lineItem.pricing.extended_price">
                  · Total {{ displayCurrency }} {{ displayPrice(lineItem.pricing.extended_price) }}
                </span>
              </p>
              <p
                v-for="issue in issuesForField(['pricing.discount', 'pricing.extended_price'])"
                :key="`${issue.field_path}:${issue.code}`"
                class="mt-1 text-[11px] text-amber-700"
              >
                ⚠ {{ mappingIssueText(issue) }}
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
                <span class="font-bold">{{ displayCurrency }} {{ displayPrice(tier.price) }} / {{ tier.price_uom || "unit" }}</span>
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
          <details v-if="mappingIssuesFor('quantity_packaging').length" class="mb-3 border-l-2 border-amber-500 bg-surface-alt px-3 py-2 text-[11px] text-ink-2">
            <summary class="flex cursor-pointer items-center justify-between gap-3 font-semibold marker:text-amber-600">
              <span>{{ mappingIssuesFor('quantity_packaging').length }} mapping {{ mappingIssuesFor('quantity_packaging').length === 1 ? "issue" : "issues" }}</span>
              <span class="text-[10px] font-medium text-ink-3">View details</span>
            </summary>
            <div class="mt-2 space-y-1 border-t border-amber-200 pt-2">
              <p v-for="issue in mappingIssuesFor('quantity_packaging')" :key="`${issue.field_path}:${issue.code}`">{{ mappingIssueText(issue) }}</p>
            </div>
          </details>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <div class="flex items-center gap-1.5">
                <span class="text-[10px] font-bold uppercase text-slate-400">Quoted Quantity</span>
                <span
                  v-if="issuesForField(['quantity.quoted_quantity', 'quantity.quantity_basis']).length"
                  class="rounded bg-amber-100 px-1.5 py-0.5 text-[9px] font-semibold text-amber-800"
                >
                  Mapping issue
                </span>
              </div>
              <p class="font-bold text-slate-800">
                {{ displayValue(lineItem.quantity.quoted_quantity) }} {{ lineItem.quantity.quoted_quantity_uom || "" }}
              </p>
              <p
                v-for="issue in issuesForField(['quantity.quoted_quantity', 'quantity.quantity_basis'])"
                :key="`${issue.field_path}:${issue.code}`"
                class="mt-1 text-[11px] text-amber-700"
              >
                ⚠ {{ mappingIssueText(issue) }}
              </p>
            </div>
            <div>
              <div class="flex items-center gap-1.5">
                <span class="text-[10px] font-bold uppercase text-slate-400">Minimum Order Qty (MOQ)</span>
                <span
                  v-if="issuesForField('quantity.minimum_order_quantity').length"
                  class="rounded bg-amber-100 px-1.5 py-0.5 text-[9px] font-semibold text-amber-800"
                >
                  Mapping issue
                </span>
              </div>
              <p class="font-medium text-slate-800">
                {{ displayValue(lineItem.quantity.minimum_order_quantity) }} {{ lineItem.quantity.minimum_order_quantity_uom || "" }}
              </p>
              <p
                v-for="issue in issuesForField('quantity.minimum_order_quantity')"
                :key="`${issue.field_path}:${issue.code}`"
                class="mt-1 text-[11px] text-amber-700"
              >
                ⚠ {{ mappingIssueText(issue) }}
              </p>
            </div>
            <div>
              <div class="flex items-center gap-1.5">
                <span class="text-[10px] font-bold uppercase text-slate-400">Primary Pack</span>
                <span
                  v-if="issuesForField('packaging.primary_pack').length"
                  class="rounded bg-amber-100 px-1.5 py-0.5 text-[9px] font-semibold text-amber-800"
                >
                  Mapping issue
                </span>
              </div>
              <p class="font-medium text-slate-800">{{ lineItem.packaging.primary_pack || "—" }}</p>
              <p
                v-for="issue in issuesForField('packaging.primary_pack')"
                :key="`${issue.field_path}:${issue.code}`"
                class="mt-1 text-[11px] text-amber-700"
              >
                ⚠ {{ mappingIssueText(issue) }}
              </p>
            </div>
            <div>
              <div class="flex items-center gap-1.5">
                <span class="text-[10px] font-bold uppercase text-slate-400">Units Per Pack</span>
                <span
                  v-if="issuesForField('packaging.units_per_pack').length"
                  class="rounded bg-amber-100 px-1.5 py-0.5 text-[9px] font-semibold text-amber-800"
                >
                  Mapping issue
                </span>
              </div>
              <p class="font-medium text-slate-800">
                {{ lineItem.packaging.units_per_pack ? `${lineItem.packaging.units_per_pack} ${lineItem.packaging.unit_label || "units"}` : "—" }}
              </p>
              <p
                v-for="issue in issuesForField('packaging.units_per_pack')"
                :key="`${issue.field_path}:${issue.code}`"
                class="mt-1 text-[11px] text-amber-700"
              >
                ⚠ {{ mappingIssueText(issue) }}
              </p>
            </div>
            <div>
              <div class="flex items-center gap-1.5">
                <span class="text-[10px] font-bold uppercase text-slate-400">Packs Per Shipper</span>
                <span
                  v-if="issuesForField('packaging.packs_per_shipper').length"
                  class="rounded bg-amber-100 px-1.5 py-0.5 text-[9px] font-semibold text-amber-800"
                >
                  Mapping issue
                </span>
              </div>
              <p class="font-medium text-slate-800">
                {{ lineItem.packaging.packs_per_shipper ? `${lineItem.packaging.packs_per_shipper} packs / shipper` : "—" }}
              </p>
              <p
                v-for="issue in issuesForField('packaging.packs_per_shipper')"
                :key="`${issue.field_path}:${issue.code}`"
                class="mt-1 text-[11px] text-amber-700"
              >
                ⚠ {{ mappingIssueText(issue) }}
              </p>
            </div>
            <div>
              <div class="flex items-center gap-1.5">
                <span class="text-[10px] font-bold uppercase text-slate-400">Presentation</span>
                <span
                  v-if="issuesForField(['packaging.presentation', 'packaging.description']).length"
                  class="rounded bg-amber-100 px-1.5 py-0.5 text-[9px] font-semibold text-amber-800"
                >
                  Mapping issue
                </span>
              </div>
              <p class="font-medium text-slate-800">{{ lineItem.packaging.presentation || "—" }}</p>
              <p
                v-for="issue in issuesForField(['packaging.presentation', 'packaging.description'])"
                :key="`${issue.field_path}:${issue.code}`"
                class="mt-1 text-[11px] text-amber-700"
              >
                ⚠ {{ mappingIssueText(issue) }}
              </p>
            </div>
          </div>
        </div>

        <!-- Section 4: Supply & Logistics -->
        <div class="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
          <h3 class="text-xs font-bold uppercase tracking-wider text-slate-400 border-b border-slate-100 pb-2 mb-3">
            Supply & Logistics
          </h3>
          <details v-if="mappingIssuesFor('supply').length" class="mb-3 border-l-2 border-amber-500 bg-surface-alt px-3 py-2 text-[11px] text-ink-2">
            <summary class="flex cursor-pointer items-center justify-between gap-3 font-semibold marker:text-amber-600">
              <span>{{ mappingIssuesFor('supply').length }} mapping {{ mappingIssuesFor('supply').length === 1 ? "issue" : "issues" }}</span>
              <span class="text-[10px] font-medium text-ink-3">View details</span>
            </summary>
            <div class="mt-2 space-y-1 border-t border-amber-200 pt-2">
              <p v-for="issue in mappingIssuesFor('supply')" :key="`${issue.field_path}:${issue.code}`">{{ mappingIssueText(issue) }}</p>
            </div>
          </details>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <div class="flex items-center gap-1.5">
                <span class="text-[10px] font-bold uppercase text-slate-400">Lead Time</span>
                <span
                  v-if="issuesForField('supply.lead_time').length"
                  class="rounded bg-amber-100 px-1.5 py-0.5 text-[9px] font-semibold text-amber-800"
                >
                  Mapping issue
                </span>
              </div>
              <p class="font-medium text-slate-800">
                {{ displayLeadTime(lineItem.supply) }}
              </p>
              <p
                v-for="issue in issuesForField('supply.lead_time')"
                :key="`${issue.field_path}:${issue.code}`"
                class="mt-1 text-[11px] text-amber-700"
              >
                ⚠ {{ mappingIssueText(issue) }}
              </p>
            </div>
            <div>
              <div class="flex items-center gap-1.5">
                <span class="text-[10px] font-bold uppercase text-slate-400">Shipping Transit</span>
                <span
                  v-if="issuesForField('commercial_terms.transit_time').length"
                  class="rounded bg-amber-100 px-1.5 py-0.5 text-[9px] font-semibold text-amber-800"
                >
                  Mapping issue
                </span>
              </div>
              <p class="font-medium text-slate-800">
                {{ displayTransitDuration }}
              </p>
              <p
                v-for="issue in issuesForField('commercial_terms.transit_time')"
                :key="`${issue.field_path}:${issue.code}`"
                class="mt-1 text-[11px] text-amber-700"
              >
                ⚠ {{ mappingIssueText(issue) }}
              </p>
            </div>
            <div>
              <div class="flex items-center gap-1.5">
                <span class="text-[10px] font-bold uppercase text-slate-400">Shelf Life</span>
                <span
                  v-if="issuesForField('supply.shelf_life').length"
                  class="rounded bg-amber-100 px-1.5 py-0.5 text-[9px] font-semibold text-amber-800"
                >
                  Mapping issue
                </span>
              </div>
              <p class="font-medium text-slate-800">
                {{ lineItem.supply.shelf_life_months ? `${lineItem.supply.shelf_life_months} months` : "—" }}
                <span v-if="lineItem.supply.minimum_remaining_shelf_life_percent">
                  (min {{ lineItem.supply.minimum_remaining_shelf_life_percent }}% remaining)
                </span>
              </p>
              <p
                v-for="issue in issuesForField('supply.shelf_life')"
                :key="`${issue.field_path}:${issue.code}`"
                class="mt-1 text-[11px] text-amber-700"
              >
                ⚠ {{ mappingIssueText(issue) }}
              </p>
            </div>
            <div>
              <div class="flex items-center gap-1.5">
                <span class="text-[10px] font-bold uppercase text-slate-400">Cold Chain</span>
                <span
                  v-if="issuesForField('supply.cold_chain_required').length"
                  class="rounded bg-amber-100 px-1.5 py-0.5 text-[9px] font-semibold text-amber-800"
                >
                  Mapping issue
                </span>
              </div>
              <p class="font-medium text-slate-800">
                {{ lineItem.supply.cold_chain_required != null ? (lineItem.supply.cold_chain_required ? "Required" : "Not required") : "—" }}
              </p>
              <p
                v-for="issue in issuesForField('supply.cold_chain_required')"
                :key="`${issue.field_path}:${issue.code}`"
                class="mt-1 text-[11px] text-amber-700"
              >
                ⚠ {{ mappingIssueText(issue) }}
              </p>
            </div>
            <div class="sm:col-span-2">
              <div class="flex items-center gap-1.5">
                <span class="text-[10px] font-bold uppercase text-slate-400">Storage Conditions</span>
                <span
                  v-if="issuesForField('supply.storage_conditions').length"
                  class="rounded bg-amber-100 px-1.5 py-0.5 text-[9px] font-semibold text-amber-800"
                >
                  Mapping issue
                </span>
              </div>
              <p class="font-medium text-slate-800">{{ lineItem.supply.storage_conditions || "—" }}</p>
              <p
                v-for="issue in issuesForField('supply.storage_conditions')"
                :key="`${issue.field_path}:${issue.code}`"
                class="mt-1 text-[11px] text-amber-700"
              >
                ⚠ {{ mappingIssueText(issue) }}
              </p>
            </div>
          </div>
        </div>

        <!-- Section 5: Regulatory & Compliance -->
        <div class="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
          <h3 class="text-xs font-bold uppercase tracking-wider text-slate-400 border-b border-slate-100 pb-2 mb-3">
            Regulatory & Compliance
          </h3>
          <details v-if="mappingIssuesFor('regulatory').length" class="mb-3 border-l-2 border-amber-500 bg-surface-alt px-3 py-2 text-[11px] text-ink-2">
            <summary class="flex cursor-pointer items-center justify-between gap-3 font-semibold marker:text-amber-600">
              <span>{{ mappingIssuesFor('regulatory').length }} mapping {{ mappingIssuesFor('regulatory').length === 1 ? "issue" : "issues" }}</span>
              <span class="text-[10px] font-medium text-ink-3">View details</span>
            </summary>
            <div class="mt-2 space-y-1 border-t border-amber-200 pt-2">
              <p v-for="issue in mappingIssuesFor('regulatory')" :key="`${issue.field_path}:${issue.code}`">{{ mappingIssueText(issue) }}</p>
            </div>
          </details>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <div class="flex items-center gap-1.5">
                <span class="text-[10px] font-bold uppercase text-slate-400">WHO Prequalified</span>
                <span
                  v-if="issuesForField('regulatory.who_prequalified').length"
                  class="rounded bg-amber-100 px-1.5 py-0.5 text-[9px] font-semibold text-amber-800"
                >
                  Mapping issue
                </span>
              </div>
              <p class="font-medium text-slate-800">
                <span v-if="lineItem.regulatory?.who_prequalified != null">
                  {{ lineItem.regulatory.who_prequalified ? `WHO prequalified${lineItem.regulatory.who_pq_reference ? ` · ${lineItem.regulatory.who_pq_reference}` : ""}` : "WHO not prequalified" }}
                </span>
                <span v-else>—</span>
              </p>
              <p
                v-for="issue in issuesForField('regulatory.who_prequalified')"
                :key="`${issue.field_path}:${issue.code}`"
                class="mt-1 text-[11px] text-amber-700"
              >
                ⚠ {{ mappingIssueText(issue) }}
              </p>
            </div>
            <div>
              <div class="flex items-center gap-1.5">
                <span class="text-[10px] font-bold uppercase text-slate-400">Registered Markets</span>
                <span
                  v-if="issuesForField('regulatory.registered_markets').length"
                  class="rounded bg-amber-100 px-1.5 py-0.5 text-[9px] font-semibold text-amber-800"
                >
                  Mapping issue
                </span>
              </div>
              <p class="font-medium text-slate-800">
                {{ lineItem.regulatory?.registered_markets?.length ? `markets: ${lineItem.regulatory.registered_markets.join(", ")}` : "—" }}
              </p>
              <p
                v-for="issue in issuesForField('regulatory.registered_markets')"
                :key="`${issue.field_path}:${issue.code}`"
                class="mt-1 text-[11px] text-amber-700"
              >
                ⚠ {{ mappingIssueText(issue) }}
              </p>
            </div>
            <div>
              <div class="flex items-center gap-1.5">
                <span class="text-[10px] font-bold uppercase text-slate-400">Regulatory Status</span>
                <span
                  v-if="issuesForField(['regulatory.regulatory_status', 'regulatory.registration_reference']).length"
                  class="rounded bg-amber-100 px-1.5 py-0.5 text-[9px] font-semibold text-amber-800"
                >
                  Mapping issue
                </span>
              </div>
              <p class="font-medium text-slate-800">{{ lineItem.regulatory?.regulatory_status || "—" }}</p>
              <p
                v-for="issue in issuesForField(['regulatory.regulatory_status', 'regulatory.registration_reference'])"
                :key="`${issue.field_path}:${issue.code}`"
                class="mt-1 text-[11px] text-amber-700"
              >
                ⚠ {{ mappingIssueText(issue) }}
              </p>
            </div>
          </div>
        </div>
      </div>
    </aside>
  </div>
</template>
