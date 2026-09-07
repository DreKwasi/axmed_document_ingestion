<script setup lang="ts">
import { computed } from "vue";
import type { DocumentResponse } from "@/types";
import { sourceDocumentUrl } from "@/api";

const props = defineProps<{
  document: DocumentResponse;
  busy: boolean;
}>();

const emit = defineEmits<{
  (event: "back"): void;
  (event: "openReview"): void;
  (event: "confirmMapping"): void;
}>();

function statusKey(doc: DocumentResponse): "ready" | "review" | "needs_attention" | "processing" {
  if (doc.quotation?.review_status === "approved") return "ready";
  if (["failed", "rejected"].includes(doc.status) || doc.quotation?.review_status === "rejected") return "needs_attention";
  if (doc.status === "approved") return "ready";
  if (doc.status === "pending_review") return "review";
  return "processing";
}

const statusLabel = computed(() => {
  if (props.document.status === "pending_review" && props.document.quotation?.has_corrections) return "Pending review after correction";
  const map = {
    ready: "Ready",
    review: "Pending human review",
    needs_attention: "Needs attention",
    processing: "Processing",
  };
  return map[statusKey(props.document)];
});

const sourceTitle = computed(() => {
  if (props.document.source_name) return props.document.source_name;
  const supplier = props.document.quotation?.supplier.name;
  const ref = props.document.quotation?.quotation_reference;
  if (supplier && ref) return `${supplier} · ${ref}`;
  if (supplier) return `${supplier} quotation`;
  const filename = props.document.filename.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").trim();
  return filename.replace(/\b\w/g, (c) => c.toUpperCase()) || "Untitled source";
});

const confidence = computed(() => {
  const summary = props.document.confidence_summary;
  if (!summary) return "Confidence pending";
  if (summary.Low) return "Low confidence";
  if (summary.Medium) return "Medium confidence";
  if (summary.High) return "High confidence";
  return "Confidence unavailable";
});

const hsCodes = computed(() => props.document.quotation?.commercial_terms.hs_codes?.filter(Boolean) ?? []);

const formatBadge = computed(() => {
  const lower = props.document.filename.toLowerCase();
  if (lower.endsWith(".pdf")) return "PDF";
  if (lower.endsWith(".json")) return "JSON";
  if (lower.endsWith(".eml")) return "EML";
  if (lower.endsWith(".png") || lower.endsWith(".jpg") || lower.endsWith(".jpeg")) return "IMAGE";
  return props.document.source_system?.toUpperCase() || "FILE";
});

const canReview = computed(() => {
  return (
    props.document.status === "pending_review" &&
    props.document.quotation?.review_status === "pending_review"
  );
});

const statusTextClass = computed(() => {
  const map = {
    ready: "text-emerald-700",
    review: "text-teal-700",
    needs_attention: "text-rose-600",
    processing: "text-slate-500",
  };
  return map[statusKey(props.document)];
});

const statusDotClass = computed(() => {
  const map = {
    ready: "bg-emerald-600",
    review: "bg-teal-500",
    needs_attention: "bg-rose-500",
    processing: "bg-slate-400 animate-pulse",
  };
  return map[statusKey(props.document)];
});
</script>

<template>
  <div class="space-y-4">
    <!-- Back link -->
    <div>
      <button
        type="button"
        class="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-emerald-700 transition"
        @click="emit('back')"
      >
        <span>←</span> Back to sources
      </button>
    </div>

    <!-- Main Header Card -->
    <div class="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs">
      <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div class="space-y-2">
          <!-- Document Title -->
          <h1 class="text-2xl font-extrabold tracking-tight text-slate-900 sm:text-3xl">
            {{ sourceTitle }}
          </h1>

          <!-- Informational Metadata Line (Clean text & status dot, NOT buttons) -->
          <div class="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-slate-600">
            <!-- Format Tag -->
            <span class="rounded-md bg-slate-100 px-2 py-0.5 text-[10px] font-mono font-bold uppercase tracking-wider text-slate-600 border border-slate-200/80">
              {{ formatBadge }}
            </span>

            <!-- Filename -->
            <span class="font-mono text-slate-500 text-[11px]">{{ document.filename }}</span>

            <span class="text-slate-300">·</span>

            <!-- Source confidence is the lowest extracted-field band, not an average. -->
            <span class="font-medium text-slate-600">
              {{ confidence }}
            </span>

            <span class="text-slate-300">·</span>

            <!-- Status Indicator with dot -->
            <span class="inline-flex items-center gap-1.5 font-semibold" :class="statusTextClass">
              <span class="h-2 w-2 rounded-full" :class="statusDotClass"></span>
              {{ statusLabel }}
            </span>
          </div>
        </div>

        <!-- Distinct Action Buttons -->
        <div class="flex items-center gap-3 shrink-0">
          <!-- Secondary Action: Open Original -->
          <a
            class="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 hover:text-slate-900 hover:border-slate-300 transition shadow-2xs"
            :href="sourceDocumentUrl(document.id)"
            target="_blank"
            rel="noreferrer"
          >
            <span>Open original</span>
            <span class="text-slate-400 text-xs font-mono">↗</span>
          </a>

          <!-- Primary CTA Action: Review Source -->
          <button
            v-if="canReview"
            type="button"
            class="inline-flex items-center gap-1.5 rounded-xl bg-emerald-800 px-4 py-2 text-xs font-bold text-white shadow-xs hover:bg-emerald-900 transition focus:outline-none focus:ring-2 focus:ring-emerald-700 focus:ring-offset-1 disabled:opacity-50"
            :disabled="busy"
            @click="emit('openReview')"
          >
            <span class="text-emerald-300">✓</span>
            <span>Review source</span>
          </button>
        </div>
      </div>

      <!-- Schema and Extraction Metadata Strip -->
      <div class="mt-5 border-t border-slate-100 pt-4">
        <div class="grid grid-cols-2 gap-3 md:grid-cols-5 text-xs">
          <div class="rounded-xl bg-slate-50 p-3 border border-slate-100">
            <p class="text-[10px] font-bold uppercase tracking-wider text-slate-400">Source Schema / System</p>
            <p class="mt-1 font-semibold text-slate-800">
              {{ document.source_system || "Standard" }}
              <span v-if="document.schema_version" class="text-slate-500 text-[11px]">v{{ document.schema_version }}</span>
              <span v-if="document.parsed_summary?.page_count" class="text-slate-500 text-[11px]">
                · {{ document.parsed_summary.page_count }} pages
              </span>
            </p>
          </div>

          <div class="rounded-xl bg-slate-50 p-3 border border-slate-100">
            <p class="text-[10px] font-bold uppercase tracking-wider text-slate-400">Supplier</p>
            <p class="mt-1 font-semibold text-slate-800 truncate" :title="document.quotation?.supplier.name ?? '—'">
              {{ document.quotation?.supplier.name || "—" }}
              <span v-if="document.quotation?.supplier.country" class="text-slate-500 text-[11px]">
                ({{ document.quotation.supplier.country }})
              </span>
            </p>
          </div>

          <div class="rounded-xl bg-slate-50 p-3 border border-slate-100">
            <p class="text-[10px] font-bold uppercase tracking-wider text-slate-400">Delivery Terms</p>
            <p class="mt-1 font-semibold text-slate-800">
              {{ document.quotation?.commercial_terms.currency || "USD" }}
              <span v-if="document.quotation?.commercial_terms.incoterm" class="text-slate-600">
                · {{ document.quotation.commercial_terms.incoterm }}
              </span>
              <span v-if="document.quotation?.commercial_terms.incoterm_named_place" class="text-slate-500 text-[11px]">
                ({{ document.quotation.commercial_terms.incoterm_named_place }})
              </span>
            </p>
            <p v-if="document.quotation?.commercial_terms.incoterm_country" class="mt-1 text-[11px] text-slate-500">
              Delivery country: {{ document.quotation.commercial_terms.incoterm_country }}
            </p>
            <p v-if="hsCodes.length" class="mt-1 text-[11px] text-slate-500">
              HS codes: {{ hsCodes.join(" · ") }}
            </p>
          </div>

          <div class="rounded-xl bg-slate-50 p-3 border border-slate-100">
            <p class="text-[10px] font-bold uppercase tracking-wider text-slate-400">Document Type / Ref</p>
            <p class="mt-1 font-semibold text-slate-800 truncate" :title="document.quotation?.quotation_reference ?? '—'">
              {{ document.quotation?.quotation_reference || "—" }}
              <span v-if="document.quotation?.document_type" class="text-slate-500 text-[11px]">
                · {{ document.quotation.document_type }}
              </span>
            </p>
          </div>

          <div class="rounded-xl bg-slate-50 p-3 border border-slate-100">
            <p class="text-[10px] font-bold uppercase tracking-wider text-slate-400">Against RFQ</p>
            <p class="mt-1 font-semibold text-slate-800 truncate" :title="document.quotation?.rfq_reference ?? '—'">
              {{ document.quotation?.rfq_reference || "—" }}
            </p>
          </div>
        </div>
      </div>
    </div>

    <!-- Mapping Confirmation Checkpoint Banner (if new schema detected) -->
    <div
      v-if="document.status === 'needs_mapping_confirmation'"
      class="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-xs text-amber-900"
    >
      <div>
        <p class="font-bold text-amber-950">New source structure detected</p>
        <p class="mt-0.5 text-amber-800">
          The system proposed a mapping for {{ document.source_system || 'this schema' }}. Confirm the mapping to proceed with review.
        </p>
      </div>
      <button
        type="button"
        class="rounded-xl bg-amber-800 px-4 py-2 font-bold text-white hover:bg-amber-900 transition disabled:opacity-50"
        :disabled="busy"
        @click="emit('confirmMapping')"
      >
        Confirm mapping
      </button>
    </div>
  </div>
</template>
