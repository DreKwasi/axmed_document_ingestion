<script setup lang="ts">
import { ref } from "vue";
import type { LineItem } from "@/types";

const props = defineProps<{
  lineItems: LineItem[];
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

const activeMappingTooltip = ref<number | null>(null);
const showMappingDefinition = ref(false);

function displayValue(value: string | number | boolean | null | undefined) {
  if (value == null || value === "") return "—";
  if (typeof value === "string" && /^\d{4,}$/.test(value)) return Number(value).toLocaleString();
  return String(value);
}

function displayPrice(value: string | null | undefined) {
  if (value == null) return "—";
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric.toLocaleString(undefined, { maximumFractionDigits: 6 }) : value;
}

function mappingConfidenceForLine(index: number): number | null {
  const values = props.fieldReviews
    ?.filter((field) => field.field_path.startsWith(`line_items[${index}]`))
    .map((field) => field.mapping_confidence_score)
    .filter((score): score is number => score != null) ?? [];
  return values.length ? Math.round(values.reduce((sum, score) => sum + score, 0) / values.length) : null;
}

function mappingConfidenceExplanation(index: number): string {
  const fields = props.fieldReviews?.filter((field) => field.field_path.startsWith(`line_items[${index}]`)) ?? [];
  const scores = fields.map((field) => field.mapping_confidence_score).filter((score): score is number => score != null);
  if (!scores.length) return "No mapped fields are available to assess.";
  const reasons = [...new Set(fields.map((field) => field.mapping_confidence_reason).filter((reason): reason is string => Boolean(reason)))];
  const issueCount = mappingIssueCountForLine(index);
  return `Average of ${scores.length} mapped field score${scores.length === 1 ? "" : "s"}: ${mappingConfidenceForLine(index)}%. ${reasons.join(" ")} Mapping issues are counted separately: ${issueCount}.`;
}

function confidenceBadgeClass(confidence: number | null): string {
  if (confidence == null) return "bg-slate-100 text-slate-600 border-slate-200";
  if (confidence >= 85) return "bg-emerald-50 text-emerald-700 border-emerald-200";
  if (confidence >= 65) return "bg-amber-50 text-amber-700 border-amber-200";
  if (confidence < 65) return "bg-rose-50 text-rose-700 border-rose-200";
  return "bg-slate-100 text-slate-600 border-slate-200";
}

function mappingIssueCountForLine(index: number): number {
  const prefix = `line_items[${index}]`;
  return props.mappingIssues.filter((issue) => issue.field_path.startsWith(prefix)).length;
}

function toggleMappingTooltip(index: number) {
  activeMappingTooltip.value = activeMappingTooltip.value === index ? null : index;
}
</script>

<template>
  <div class="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xs">
    <div class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-6 py-4">
      <div>
        <h2 class="text-base font-bold text-slate-900">Product breakdown</h2>
        <p class="mt-0.5 text-xs text-slate-500">
          {{ lineItems.length }} extracted products · Mapping confidence reflects certainty that values landed on the right schema fields.
        </p>
      </div>
    </div>

    <div class="overflow-x-auto">
      <table class="w-full text-left text-xs">
        <thead class="bg-slate-50 text-[10px] font-bold uppercase tracking-wider text-slate-500 border-b border-slate-100">
          <tr>
            <th class="px-6 py-3.5">Product</th>
            <th class="px-4 py-3.5">Dosage form</th>
            <th class="px-4 py-3.5">Quoted quantity</th>
            <th class="px-4 py-3.5">Quoted Price</th>
            <th class="relative px-4 py-3.5">
              <span class="inline-flex items-center gap-1">
                Mapping confidence
                <button
                  type="button"
                  class="flex h-4 w-4 items-center justify-center rounded-full border border-slate-400 text-[9px] font-bold normal-case hover:border-emerald-700 hover:text-emerald-700"
                  aria-label="How mapping confidence is calculated"
                  :aria-expanded="showMappingDefinition"
                  @click.stop="showMappingDefinition = !showMappingDefinition"
                >
                  ?
                </button>
              </span>
              <span
                v-if="showMappingDefinition"
                role="tooltip"
                class="absolute left-4 top-10 z-50 w-80 rounded-lg border border-slate-200 bg-white p-3 text-left text-[11px] font-normal normal-case leading-4 tracking-normal text-slate-700 shadow-lg"
              >
                <span class="font-semibold text-slate-900">How mapping confidence is built</span>
                <span class="mt-1 block">We score each mapped field based on whether the source value is attached to the correct schema field, has reliable source provenance, matches the expected value category, and agrees with related values. The product score is the average of those field scores.</span>
                <span class="mt-1 block">Mapping issues are counted separately and do not represent missing fields.</span>
              </span>
            </th>
            <th class="px-4 py-3.5">Mapping issues</th>
            <th class="px-4 py-3.5 text-right"></th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr
            v-for="(item, index) in lineItems"
            :key="item.source_key ?? index"
            class="group cursor-pointer transition hover:bg-slate-50/80"
            :class="selectedIndex === index ? 'bg-emerald-50/40' : ''"
            @click="emit('selectLine', index)"
          >
            <!-- Product Trade Name & INN -->
            <td class="px-6 py-4 align-top">
              <span class="block font-bold text-slate-900 group-hover:text-emerald-800 transition">
                {{ item.product.trade_name || "Unnamed product" }}
              </span>
              <span class="mt-0.5 block text-slate-500 text-[11px]">
                {{ item.product.inn.join(" · ") || "INN not specified" }}
              </span>
            </td>

            <!-- Dosage form -->
            <td class="px-4 py-4 align-top text-slate-700">
              <span class="block font-medium">
                {{ item.product.dosage_form || "—" }}
              </span>
            </td>

            <!-- Quoted Quantity -->
            <td class="px-4 py-4 align-top text-slate-800">
              <span class="font-bold">{{ displayValue(item.quantity.quoted_quantity) }} {{ item.quantity.quoted_quantity_uom || "" }}</span>
              <span
                v-if="item.quantity.minimum_order_quantity"
                class="mt-0.5 block text-[11px] text-slate-400 font-normal"
              >
                MOQ: {{ displayValue(item.quantity.minimum_order_quantity) }} {{ item.quantity.minimum_order_quantity_uom || "" }}
              </span>
            </td>

            <!-- Quoted Price -->
            <td class="px-4 py-4 align-top text-slate-800">
              <span class="font-bold">
                {{ item.pricing.currency || "" }} {{ displayPrice(item.pricing.quoted_price.amount) }}
              </span>
              <span v-if="item.pricing.quoted_price.uom" class="text-slate-500">
                / {{ item.pricing.quoted_price.uom }}
              </span>
            </td>

            <td class="px-4 py-4 align-top">
              <span class="relative inline-flex">
                <button
                  type="button"
                  class="inline-flex items-center rounded-lg border px-2.5 py-1 text-[11px] font-bold"
                  :class="confidenceBadgeClass(mappingConfidenceForLine(index))"
                  :aria-expanded="activeMappingTooltip === index"
                  :title="mappingConfidenceExplanation(index)"
                  aria-label="Explain mapping confidence"
                  @click.stop="toggleMappingTooltip(index)"
                >
                  {{ mappingConfidenceForLine(index) != null ? `${mappingConfidenceForLine(index)}%` : (mappingIssueCountForLine(index) === 0 ? "No issues" : "Needs review") }}
                </button>
                <span
                  v-if="activeMappingTooltip === index"
                  role="tooltip"
                  class="absolute left-0 top-8 z-50 w-72 rounded-lg border border-slate-200 bg-white p-3 text-[11px] font-normal leading-4 text-slate-700 shadow-lg"
                >
                  {{ mappingConfidenceExplanation(index) }}
                </span>
              </span>
            </td>

            <td class="px-4 py-4 align-top">
              <span
                class="inline-flex min-w-7 items-center justify-center rounded-lg border px-2.5 py-1 text-[11px] font-bold"
                :class="mappingIssueCountForLine(index) > 0
                  ? 'border-rose-200 bg-rose-50 text-rose-700'
                  : 'border-slate-200 bg-slate-50 text-slate-500'"
              >
                {{ mappingIssueCountForLine(index) }}
              </span>
            </td>

            <!-- Action -->
            <td class="px-4 py-4 align-top text-right">
              <button
                type="button"
                class="rounded-lg px-2.5 py-1 text-xs font-semibold text-emerald-700 hover:bg-emerald-50 hover:text-emerald-800 transition"
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
