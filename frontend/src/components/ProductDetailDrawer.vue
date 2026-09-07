<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { DocumentResponse, LineItem } from "@/types";

const props = defineProps<{
  isOpen: boolean;
  document: DocumentResponse;
  lineItem: LineItem | null;
  lineIndex: number;
  busy: boolean;
}>();

const emit = defineEmits<{
  (event: "close"): void;
  (event: "saveCorrection", payload: { fieldPath: string; value: string; lineIndex: number }): void;
}>();

const selectedField = ref("pricing.pack_price");
const correctionValue = ref("");

// Pre-fill correctionValue when selectedField or lineItem changes
watch(
  [() => props.lineItem, selectedField, () => props.isOpen],
  () => {
    if (!props.lineItem) {
      correctionValue.value = "";
      return;
    }
    const item = props.lineItem;
    if (selectedField.value === "pricing.pack_price") {
      correctionValue.value = item.pricing.pack_price ?? item.pricing.quoted_price?.amount ?? "";
    } else if (selectedField.value === "quantity.quoted_quantity") {
      correctionValue.value = item.quantity.quoted_quantity ?? "";
    } else if (selectedField.value === "quantity.minimum_order_quantity") {
      correctionValue.value = item.quantity.minimum_order_quantity ?? "";
    } else if (selectedField.value === "packaging.units_per_pack") {
      correctionValue.value = item.packaging.units_per_pack ? String(item.packaging.units_per_pack) : "";
    } else if (selectedField.value === "product.trade_name") {
      correctionValue.value = item.product.trade_name ?? "";
    } else {
      correctionValue.value = "";
    }
  },
  { immediate: true }
);

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

const rowConfidence = computed(() => {
  if (!props.lineItem?.evidence?.length) return "—";
  const scores = props.lineItem.evidence
    .map((e) => Number(e.confidence))
    .filter((n) => !isNaN(n) && n > 0);
  if (!scores.length) return "—";
  const avg = scores.reduce((sum, val) => sum + val, 0) / scores.length;
  return `${Math.round(avg * 100)}%`;
});

function handleSave() {
  if (!correctionValue.value.trim()) return;
  const path = `line_items.${props.lineIndex}.${selectedField.value}`;
  emit("saveCorrection", {
    fieldPath: path,
    value: correctionValue.value.trim(),
    lineIndex: props.lineIndex,
  });
}
</script>

<template>
  <div
    v-if="isOpen && lineItem"
    class="fixed inset-0 z-40 flex justify-end bg-slate-900/40 backdrop-blur-xs transition-opacity"
    role="dialog"
    aria-modal="true"
    aria-labelledby="product-drawer-title"
    @click.self="emit('close')"
  >
    <div
      class="flex h-full w-full max-w-2xl flex-col border-l border-slate-200 bg-white shadow-2xl transition-transform"
    >
      <!-- Drawer Header -->
      <div class="flex items-center justify-between border-b border-slate-200 px-6 py-4 bg-slate-50/50">
        <div>
          <div class="flex items-center gap-2">
            <span class="rounded-md bg-emerald-100 px-2 py-0.5 text-[11px] font-bold text-emerald-800">
              Line {{ lineIndex + 1 }}
            </span>
            <span class="text-xs font-semibold text-slate-500">
              Confidence: <strong class="text-emerald-700">{{ rowConfidence }}</strong>
            </span>
          </div>
          <h2 id="product-drawer-title" class="mt-1 text-lg font-bold text-slate-900">
            {{ lineItem.product.trade_name || "Product Details" }}
          </h2>
        </div>
        <button
          type="button"
          class="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition"
          aria-label="Close product details"
          @click="emit('close')"
        >
          ✕
        </button>
      </div>

      <!-- Drawer Body (Scrollable) -->
      <div class="flex-1 overflow-y-auto p-6 space-y-6 text-xs">
        <!-- Edit / Correction Card (Clean & Inline) -->
        <div class="rounded-2xl border border-emerald-200 bg-emerald-50/40 p-4 shadow-xs">
          <div class="flex items-center justify-between">
            <h3 class="text-xs font-bold uppercase tracking-wider text-emerald-900">
              Edit Product Fields
            </h3>
            <span class="text-[11px] text-emerald-700">Editable review correction</span>
          </div>
          <p class="mt-1 text-[11px] text-emerald-800">
            Select any field below to modify its value. Changes recalculate commercial terms automatically.
          </p>

          <div class="mt-3 grid grid-cols-1 sm:grid-cols-[160px_1fr_auto] gap-2 items-center">
            <select
              v-model="selectedField"
              class="rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-700 focus:border-emerald-600 focus:outline-none"
              aria-label="Correction field"
            >
              <option value="pricing.pack_price">Pack price</option>
              <option value="quantity.quoted_quantity">Quoted quantity</option>
              <option value="quantity.minimum_order_quantity">MOQ</option>
              <option value="packaging.units_per_pack">Units / pack</option>
              <option value="product.trade_name">Trade name</option>
            </select>

            <input
              v-model="correctionValue"
              class="rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs text-slate-800 focus:border-emerald-600 focus:outline-none placeholder:text-slate-400"
              :aria-label="`Correction value for ${lineItem.product.trade_name ?? lineIndex}`"
              placeholder="Enter corrected value"
              @keydown.enter="handleSave"
            />

            <button
              type="button"
              class="rounded-xl bg-emerald-700 px-4 py-2 text-xs font-bold text-white hover:bg-emerald-800 transition disabled:opacity-50 whitespace-nowrap"
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
              <span class="text-[10px] font-bold uppercase text-slate-400">Dosage Form / Route</span>
              <p class="font-medium text-slate-800">
                {{ [lineItem.product.dosage_form, lineItem.product.route].filter(Boolean).join(" · ") || "—" }}
              </p>
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
                {{ lineItem.pricing.currency }} {{ displayPrice(lineItem.pricing.normalized_price.amount) }} / {{ lineItem.pricing.normalized_price.uom || "unit" }}
              </p>
              <span v-if="lineItem.pricing.normalized_price.calculation" class="text-[10px] text-slate-400">
                Formula: {{ lineItem.pricing.normalized_price.calculation }}
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
            <span class="text-[10px] font-bold uppercase text-slate-400 block mb-1">Volume Price Tiers</span>
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
        </div>

        <!-- Section 3: Quantity & Packaging -->
        <div class="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
          <h3 class="text-xs font-bold uppercase tracking-wider text-slate-400 border-b border-slate-100 pb-2 mb-3">
            Quantity & Packaging
          </h3>
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
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <span class="text-[10px] font-bold uppercase text-slate-400">Lead Time</span>
              <p class="font-medium text-slate-800">
                {{ lineItem.supply.lead_time_days ? `${lineItem.supply.lead_time_days} days` : "—" }}
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
              <span class="text-[10px] font-bold uppercase text-slate-400">Storage Conditions</span>
              <p class="font-medium text-slate-800">{{ lineItem.supply.storage_conditions || "—" }}</p>
            </div>
            <div>
              <span class="text-[10px] font-bold uppercase text-slate-400">Cold Chain</span>
              <p class="font-medium text-slate-800">
                {{ lineItem.supply.cold_chain_required != null ? (lineItem.supply.cold_chain_required ? "Required" : "Not required") : "—" }}
              </p>
            </div>
          </div>
        </div>

        <!-- Section 5: Regulatory & Compliance -->
        <div class="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
          <h3 class="text-xs font-bold uppercase tracking-wider text-slate-400 border-b border-slate-100 pb-2 mb-3">
            Regulatory & Compliance
          </h3>
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
            <div>
              <span class="text-[10px] font-bold uppercase text-slate-400">HS / ATC Code</span>
              <p class="font-medium text-slate-800">
                {{ [lineItem.regulatory?.hs_code, lineItem.regulatory?.atc_code].filter(Boolean).join(" · ") || "—" }}
              </p>
            </div>
          </div>
        </div>

        <!-- Section 6: Evidence & Provenance -->
        <div v-if="lineItem.evidence?.length" class="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
          <h3 class="text-xs font-bold uppercase tracking-wider text-slate-400 border-b border-slate-100 pb-2 mb-3">
            Field Evidence & Provenance
          </h3>
          <div class="space-y-2">
            <div
              v-for="(ev, idx) in lineItem.evidence"
              :key="idx"
              class="flex items-center justify-between rounded-xl bg-slate-50 p-2.5 text-[11px] border border-slate-100"
            >
              <div>
                <span class="font-semibold text-slate-800">{{ ev.canonical_field }}</span>
                <span v-if="ev.source_path" class="text-slate-400 block font-mono text-[10px]">
                  Source: {{ ev.source_path }}
                </span>
              </div>
              <div class="text-right">
                <span class="font-bold text-emerald-700">
                  {{ Math.round(Number(ev.confidence) * 100) }}%
                </span>
                <span class="text-slate-400 block text-[10px]">{{ ev.extraction_method }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
