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
  if (doc.status === "needs_review") return "review";
  return "processing";
}

const statusLabel = computed(() => {
  const map = {
    ready: "Ready",
    review: "Review",
    needs_attention: "Needs attention",
    processing: "Processing",
  };
  return map[statusKey(props.document)];
});

const statusBadgeClass = computed(() => {
  const map = {
    ready: "bg-emerald-50 text-emerald-700 border-emerald-200",
    review: "bg-teal-50 text-teal-700 border-teal-200",
    needs_attention: "bg-rose-50 text-rose-700 border-rose-200",
    processing: "bg-slate-100 text-slate-600 border-slate-200",
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

const overallConfidence = computed(() => {
  if (props.document.extraction_confidence) return props.document.extraction_confidence;
  const values = props.document.quotation?.line_items.flatMap((item) =>
    item.evidence.map((evidence) => Number(evidence.confidence))
  ) ?? [];
  return values.length ? `${Math.round(Math.min(...values) * 100)}%` : "—";
});

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
    props.document.status === "needs_review" &&
    props.document.quotation?.review_status === "unreviewed"
  );
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
      <div class="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div class="flex items-center gap-2">
            <span class="rounded-md bg-slate-100 px-2 py-0.5 text-[11px] font-bold tracking-wider text-slate-600 uppercase border border-slate-200">
              {{ formatBadge }}
            </span>
            <span class="text-xs font-semibold text-slate-400">Source detail</span>
          </div>
          <h1 class="mt-1 text-2xl font-extrabold tracking-tight text-slate-900 sm:text-3xl">
            {{ sourceTitle }}
          </h1>
          <p class="mt-1 text-xs text-slate-500 font-mono break-all">
            {{ document.filename }}
          </p>
        </div>

        <div class="flex flex-wrap items-center gap-3">
          <!-- Overall Confidence Badge -->
          <div class="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2 text-xs font-semibold text-slate-700">
            <span class="text-slate-400">Confidence:</span>
            <span class="font-bold text-emerald-700">{{ overallConfidence }}</span>
          </div>

          <!-- Status Badge -->
          <span
            class="rounded-xl border px-3.5 py-2 text-xs font-bold tracking-wide uppercase"
            :class="statusBadgeClass"
          >
            {{ statusLabel }}
          </span>

          <!-- Open Original Link -->
          <a
            class="rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 hover:text-emerald-700 transition"
            :href="sourceDocumentUrl(document.id)"
            target="_blank"
            rel="noreferrer"
          >
            Open original
          </a>

          <!-- Review Button (Triggers Review Dialog) -->
          <button
            v-if="canReview"
            type="button"
            class="rounded-xl bg-emerald-800 px-4 py-2 text-xs font-bold tracking-wide text-white hover:bg-emerald-900 transition shadow-xs focus:outline-none"
            :disabled="busy"
            @click="emit('openReview')"
          >
            Review source
          </button>
        </div>
      </div>

      <!-- Schema and Extraction Metadata Strip -->
      <div class="mt-5 border-t border-slate-100 pt-4">
        <div class="grid grid-cols-2 gap-3 sm:grid-cols-4 text-xs">
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
            <p class="text-[10px] font-bold uppercase tracking-wider text-slate-400">Commercial Terms</p>
            <p class="mt-1 font-semibold text-slate-800">
              {{ document.quotation?.commercial_terms.currency || "USD" }}
              <span v-if="document.quotation?.commercial_terms.incoterm" class="text-slate-600">
                · {{ document.quotation.commercial_terms.incoterm }}
              </span>
              <span v-if="document.quotation?.commercial_terms.incoterm_named_place" class="text-slate-500 text-[11px]">
                ({{ document.quotation.commercial_terms.incoterm_named_place }})
              </span>
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
