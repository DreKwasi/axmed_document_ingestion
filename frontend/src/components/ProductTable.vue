<script setup lang="ts">
import type { LineItem } from "@/types";

const props = defineProps<{
  lineItems: LineItem[];
  reviewIssues: Array<{ field_path: string; code: string; message: string; severity: string }>;
  fieldReviews?: Array<{ field_path: string; reliability: "High" | "Medium" | "Low" | "Not extracted" }>;
  selectedIndex: number;
}>();

const emit = defineEmits<{
  (event: "selectLine", index: number): void;
}>();

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

function reliabilityForLine(index: number): string {
  const values = props.fieldReviews
    ?.filter((field) => field.field_path.startsWith(`line_items[${index}]`))
    .map((field) => field.reliability) ?? [];
  for (const reliability of ["Not extracted", "Low", "Medium", "High"] as const) {
    if (values.includes(reliability)) return reliability;
  }
  return "—";
}

function reliabilityBadgeClass(reliability: string): string {
  if (reliability === "High") return "bg-emerald-50 text-emerald-700 border-emerald-200";
  if (reliability === "Medium") return "bg-amber-50 text-amber-700 border-amber-200";
  if (reliability === "Low" || reliability === "Not extracted") return "bg-rose-50 text-rose-700 border-rose-200";
  return "bg-slate-100 text-slate-600 border-slate-200";
}

function issuesForLine(issues: Array<{ field_path: string; code?: string; message: string }>, index: number) {
  return issues.filter((issue) => issue.field_path.startsWith(`line_items[${index}]`));
}
</script>

<template>
  <div class="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xs">
    <div class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-6 py-4">
      <div>
        <h2 class="text-base font-bold text-slate-900">Product breakdown</h2>
        <p class="mt-0.5 text-xs text-slate-500">
          {{ lineItems.length }} extracted products · Click any row to inspect all columns and edit fields.
        </p>
      </div>
    </div>

    <div class="overflow-x-auto">
      <table class="w-full text-left text-xs">
        <thead class="bg-slate-50 text-[10px] font-bold uppercase tracking-wider text-slate-500 border-b border-slate-100">
          <tr>
            <th class="px-6 py-3.5">Product</th>
            <th class="px-4 py-3.5">Dosage / Presentation</th>
            <th class="px-4 py-3.5">Quoted quantity</th>
            <th class="px-4 py-3.5">Quoted Price</th>
            <th class="px-4 py-3.5">Reliability</th>
            <th class="px-4 py-3.5">Issue</th>
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
              <span v-if="item.product.manufacturer" class="mt-0.5 block text-slate-400 text-[10px]">
                {{ item.product.manufacturer }}
              </span>
            </td>

            <!-- Dosage & Route / Presentation -->
            <td class="px-4 py-4 align-top text-slate-700">
              <span class="block font-medium">
                {{ [item.product.dosage_form, item.packaging.presentation].filter(Boolean).join(" · ") || "—" }}
              </span>
              <span v-if="item.product.route" class="mt-0.5 block text-slate-400 text-[11px]">
                {{ item.product.route }}
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
              <span
                v-if="item.pricing.normalized_price?.amount"
                class="mt-0.5 block text-[11px] text-slate-500 font-normal"
              >
                Normalized: {{ item.pricing.currency }} {{ displayPrice(item.pricing.normalized_price.amount) }} / {{ item.pricing.normalized_price.uom || "unit" }}
              </span>
            </td>

            <!-- Row reliability is derived from persisted field assessments. -->
            <td class="px-4 py-4 align-top">
              <span
                class="inline-flex items-center rounded-lg border px-2.5 py-1 text-[11px] font-bold"
                :class="reliabilityBadgeClass(reliabilityForLine(index))"
              >
                {{ reliabilityForLine(index) }}
              </span>
            </td>

            <!-- Review Issues -->
            <td class="px-4 py-4 align-top">
              <div v-if="issuesForLine(reviewIssues, index).length" class="space-y-1">
                <span
                  v-for="issue in issuesForLine(reviewIssues, index)"
                  :key="issue.code"
                  class="block max-w-[180px] rounded-md bg-rose-50 px-2 py-0.5 text-[10px] font-semibold text-rose-700 border border-rose-200"
                >
                  {{ issue.message }}
                </span>
              </div>
              <span v-else class="text-slate-300">—</span>
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
