<script setup lang="ts">
/** Extracted pharmaceutical line item breakdown table. */

import { onBeforeUnmount, onMounted, ref } from "vue";
import type { LineItem } from "@/types";

// --- Section 1: Props & Emits ---

const props = defineProps<{
  lineItems: LineItem[];
  documentMappingConfidence?: number | null;
  mappingIssues: Array<{ field_path: string; code: string; message: string; severity: string }>;
  fieldReviews?: Array<{
    field_path: string;
    mapping_confidence_band: "High" | "Medium" | "Low" | null;
    mapping_confidence_score: number | null;
    mapping_confidence_reason?: string | null;
  }>;
  selectedIndex: number;
}>();

const emit = defineEmits<{
  (event: "selectLine", index: number): void;
}>();

// --- Section 2: Tooltip Controls ---

const activeMappingTooltip = ref<number | null>(null);
const showMappingDefinition = ref(false);

function closeTooltips() {
  activeMappingTooltip.value = null;
  showMappingDefinition.value = false;
}

function toggleMappingTooltip(index: number) {
  showMappingDefinition.value = false;
  activeMappingTooltip.value = activeMappingTooltip.value === index ? null : index;
}

function toggleMappingDefinition() {
  activeMappingTooltip.value = null;
  showMappingDefinition.value = !showMappingDefinition.value;
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

// --- Section 3: Formatters & Confidence Helpers ---

function displayValue(value: string | number | boolean | null | undefined): string {
  if (value == null || value === "") return "—";
  if (typeof value === "string" && /^\d{4,}$/.test(value)) return Number(value).toLocaleString();
  return String(value);
}

function displayPrice(value: string | null | undefined): string {
  if (value == null) return "—";
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric.toLocaleString(undefined, { maximumFractionDigits: 6 }) : value;
}

function mappingConfidenceForLine(index: number): number | null {
  const fields = props.fieldReviews
    ?.filter((field) => field.field_path.startsWith(`line_items[${index}]`)) ?? [];
  const values = fields
    .map((field) => field.mapping_confidence_score)
    .filter((score): score is number => score != null);
  const hasUnscoredMappedFields = fields.some(
    (field) => field.mapping_confidence_score == null
      && field.mapping_confidence_reason?.includes("precise source provenance"),
  );
  if ((!values.length || hasUnscoredMappedFields) && props.documentMappingConfidence != null) {
    return props.documentMappingConfidence;
  }
  return values.length ? Math.round(values.reduce((sum, score) => sum + score, 0) / values.length) : null;
}

function mappingConfidenceExplanation(index: number): string {
  const fields = props.fieldReviews?.filter((field) => field.field_path.startsWith(`line_items[${index}]`)) ?? [];
  const scores = fields.map((field) => field.mapping_confidence_score).filter((score): score is number => score != null);
  const hasUnscoredMappedFields = fields.some(
    (field) => field.mapping_confidence_score == null
      && field.mapping_confidence_reason?.includes("precise source provenance"),
  );
  if ((!scores.length || hasUnscoredMappedFields) && props.documentMappingConfidence != null) {
    return `This product uses the source's ${props.documentMappingConfidence}% mapping confidence because a complete product-level field score is not available.`;
  }
  if (!scores.length) return "No mapped fields are available to assess.";
  const reasons = [...new Set(fields.map((field) => field.mapping_confidence_reason).filter((reason): reason is string => Boolean(reason)))];
  const issueCount = mappingIssueCountForLine(index);
  return `Average of ${scores.length} mapped field score${scores.length === 1 ? "" : "s"}: ${mappingConfidenceForLine(index)}%. ${reasons.join(" ")} Mapping issues are counted separately: ${issueCount}.`;
}

function confidenceTextClass(confidence: number | null): string {
  if (confidence == null) return "text-ink-3";
  if (confidence >= 85) return "text-emerald-700";
  if (confidence >= 65) return "text-amber-700";
  return "text-rose-700";
}

function mappingIssueCountForLine(index: number): number {
  const prefix = `line_items[${index}]`;
  return props.mappingIssues.filter((issue) => issue.field_path.startsWith(prefix)).length;
}
</script>

<template>
  <div class="overflow-hidden rounded-2xl border border-rule bg-surface shadow-xs">
    <div class="flex flex-wrap items-center justify-between gap-3 border-b border-rule px-4 py-3 sm:px-6 sm:py-4">
      <div>
        <h2 class="text-sm sm:text-base font-bold text-ink">Product breakdown</h2>
        <p class="mt-0.5 text-xs text-ink-3">
          {{ lineItems.length }} extracted products · Mapping confidence reflects certainty that values landed on the right schema fields.
        </p>
      </div>
    </div>

    <div class="overflow-x-auto">
      <table class="w-full min-w-[640px] text-left text-xs">
        <thead class="bg-surface-alt text-[10px] font-bold uppercase tracking-wider text-ink-2 border-b border-rule">
          <tr>
            <th class="px-4 py-3 sm:px-6 sm:py-3.5">Product</th>
            <th class="px-4 py-3.5">Dosage form</th>
            <th class="px-4 py-3.5">Quoted quantity</th>
            <th class="px-4 py-3.5">Quoted Price</th>
            <th class="relative px-4 py-3.5">
              <span class="inline-flex items-center gap-1" data-tooltip-container>
                Mapping confidence
                <button
                  type="button"
                  class="flex h-4 w-4 items-center justify-center rounded-full border border-rule-dark text-[9px] font-bold normal-case hover:border-axmed-primary hover:text-axmed-primary cursor-pointer"
                  aria-label="How mapping confidence is calculated"
                  :aria-expanded="showMappingDefinition"
                  @click.stop="toggleMappingDefinition"
                >
                  ?
                </button>
              </span>
              <span
                v-if="showMappingDefinition"
                role="tooltip"
                class="absolute left-4 top-10 z-50 w-80 rounded-lg border border-rule bg-surface p-3 text-left text-[11px] font-normal normal-case leading-4 tracking-normal text-ink-2 shadow-lg"
              >
                <span class="font-semibold text-ink">How mapping confidence is built</span>
                <span class="mt-1 block">We score each mapped field based on whether the source value is attached to the correct schema field, has reliable source provenance, matches the expected value category, and agrees with related values. The product score is the average of those field scores.</span>
                <span class="mt-1 block">Mapping issues are counted separately and do not represent missing fields.</span>
              </span>
            </th>
            <th class="px-4 py-3.5 text-right"></th>
          </tr>
        </thead>
        <tbody class="divide-y divide-rule">
          <tr
            v-for="(item, index) in lineItems"
            :key="item.source_key ?? index"
            class="group cursor-pointer transition hover:bg-surface-alt/70"
            :class="selectedIndex === index ? 'bg-axmed-primary-tint' : ''"
            @click="closeTooltips(); emit('selectLine', index)"
          >
            <!-- Product Trade Name & INN -->
            <td class="px-6 py-4 align-top">
              <span class="block font-bold text-ink group-hover:text-axmed-primary transition">
                {{ item.product.trade_name || "Unnamed product" }}
              </span>
              <span class="mt-0.5 block text-ink-3 text-[11px]">
                {{ item.product.inn.join(" · ") || "INN not specified" }}
              </span>
            </td>

            <!-- Dosage form -->
            <td class="px-4 py-4 align-top text-ink-2">
              <span class="block font-medium">
                {{ item.product.dosage_form || "—" }}
              </span>
            </td>

            <!-- Quoted Quantity -->
            <td class="px-4 py-4 align-top text-ink tabular-nums">
              <span class="font-bold">{{ displayValue(item.quantity?.quoted_quantity) }} {{ item.quantity?.quoted_quantity_uom || "" }}</span>
              <span
                v-if="item.quantity?.minimum_order_quantity"
                class="mt-0.5 block text-[11px] text-ink-3 font-normal"
              >
                MOQ: {{ displayValue(item.quantity.minimum_order_quantity) }} {{ item.quantity.minimum_order_quantity_uom || "" }}
              </span>
            </td>

            <!-- Quoted Price -->
            <td class="px-4 py-4 align-top text-ink tabular-nums">
              <span class="font-bold">
                {{ item.pricing.currency || "" }} {{ displayPrice(item.pricing.quoted_price.amount) }}
              </span>
              <span v-if="item.pricing.quoted_price.uom" class="text-ink-3">
                / {{ item.pricing.quoted_price.uom }}
              </span>
            </td>

            <td class="px-4 py-4 align-top">
              <div class="relative inline-flex flex-col items-start" data-tooltip-container>
                <button
                  type="button"
                  class="text-xs font-semibold tabular-nums underline decoration-transparent underline-offset-4 transition hover:decoration-current cursor-pointer"
                  :class="confidenceTextClass(mappingConfidenceForLine(index))"
                  :aria-expanded="activeMappingTooltip === index"
                  :title="mappingConfidenceExplanation(index)"
                  aria-label="Explain mapping confidence"
                  @click.stop="toggleMappingTooltip(index)"
                >
                  {{ mappingConfidenceForLine(index) != null ? `${mappingConfidenceForLine(index)}%` : "No issues" }}
                </button>
                <span
                  class="mt-1 text-[10px] font-medium"
                  :class="mappingIssueCountForLine(index) > 0 ? 'text-rose-700' : 'text-ink-3'"
                >
                  {{ mappingIssueCountForLine(index) }} mapping {{ mappingIssueCountForLine(index) === 1 ? "issue" : "issues" }}
                </span>
                <span
                  v-if="activeMappingTooltip === index"
                  role="tooltip"
                  class="absolute left-0 top-8 z-50 w-72 rounded-lg border border-rule bg-surface p-3 text-[11px] font-normal leading-4 text-ink-2 shadow-lg"
                >
                  {{ mappingConfidenceExplanation(index) }}
                </span>
              </div>
            </td>

            <!-- Action -->
            <td class="px-4 py-4 align-top text-right">
              <button
                type="button"
                class="rounded-lg px-2.5 py-1 text-xs font-semibold text-axmed-primary hover:bg-axmed-primary-tint transition cursor-pointer"
                @click.stop="emit('selectLine', index)"
              >
                Details →
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
