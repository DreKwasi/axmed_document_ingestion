<script setup lang="ts">
import { computed } from "vue";
import type { DocumentResponse } from "@/types";
import { sourceDocumentUrl } from "@/api";

const props = defineProps<{
  document: DocumentResponse;
  busy: boolean;
  selectedApproach?: string | null;
}>();

const emit = defineEmits<{
  (event: "back"): void;
  (event: "openReview"): void;
  (event: "reextract"): void;
  (event: "switchApproach", approach: string): void;
}>();

function statusKey(doc: DocumentResponse): "ready" | "review" | "needs_attention" | "processing" {
  if (doc.quotation?.review_status === "approved") return "ready";
  if (["failed", "rejected"].includes(doc.status) || doc.quotation?.review_status === "rejected") return "needs_attention";
  if (doc.status === "approved") return "ready";
  if (doc.status === "pending_review") return "review";
  return "processing";
}

const statusLabel = computed(() => {
  if (props.document.status === "failed") return "Extraction failed";
  if (props.document.status === "rejected" || props.document.quotation?.review_status === "rejected") return "Rejected";
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
  let title = props.document.source_name;
  if (!title) {
    const supplier = props.document.quotation?.supplier.name;
    const ref = props.document.quotation?.quotation_reference;
    if (supplier && ref) title = `${supplier} · ${ref}`;
    else if (supplier) title = `${supplier} quotation`;
    else {
      const filename = props.document.filename.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").trim();
      title = filename.replace(/\b\w/g, (c) => c.toUpperCase()) || "Untitled source";
    }
  }
  if (props.selectedApproach && props.document.image_extraction_attempts?.length) {
    const suffix = props.selectedApproach === "ocr_assisted" ? "OCR-assisted" : "Direct vision";
    if (!title.includes(suffix)) {
      title = `${title} — ${suffix}`;
    }
  }
  return title;
});

const confidence = computed(() => {
  const summary = props.document.extraction_confidence;
  if (!summary) return "Extraction confidence pending";
  return `Extraction confidence ${summary.score}% (${summary.band})`;
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

const externalSystem = computed(() => {
  const rawSystem = (props.document.source_system || "").trim();
  const lower = rawSystem.toLowerCase();
  const format = formatBadge.value.toLowerCase();
  if (!rawSystem || ["pdf", "image", "eml", "email", "file", "unknown", format].includes(lower)) {
    return null;
  }
  return props.document.schema_version
    ? `${rawSystem} v${props.document.schema_version}`
    : rawSystem;
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
    <div
      v-if="document.status === 'failed' && document.failure_reason"
      class="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-950"
    >
      <p class="font-bold">Extraction failed</p>
      <p class="mt-1 text-rose-800">{{ document.failure_reason }}</p>
      <button
        v-if="document.filename.toLowerCase().endsWith('.json')"
        type="button"
        class="mt-3 rounded-lg border border-rose-300 bg-white px-3 py-1.5 text-xs font-bold text-rose-800 hover:bg-rose-100 disabled:opacity-50"
        :disabled="busy"
        @click="emit('reextract')"
      >
        Extract again
      </button>
    </div>

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

          <!-- Peer Reading Switcher (for image documents) -->
          <div
            v-if="document.image_extraction_attempts && document.image_extraction_attempts.length > 1"
            class="mt-2 inline-flex items-center gap-1 rounded-xl border border-slate-200 bg-slate-50 p-1 text-xs"
          >
            <span class="px-2 font-medium text-slate-500 text-[11px]">Reading:</span>
            <button
              v-for="attempt in document.image_extraction_attempts"
              :key="attempt.approach"
              type="button"
              class="rounded-lg px-2.5 py-1 font-semibold transition"
              :class="
                (selectedApproach || document.image_extraction_attempts[0]?.approach) === attempt.approach
                  ? 'bg-white text-emerald-900 shadow-2xs font-bold border border-slate-200/80'
                  : 'text-slate-600 hover:text-slate-900'
              "
              :disabled="busy"
              @click="emit('switchApproach', attempt.approach)"
            >
              {{ attempt.approach === "ocr_assisted" ? "OCR-assisted" : "Direct vision" }}
            </button>
          </div>

          <!-- Informational Metadata Line (Clean text & status dot, NOT buttons) -->
          <div class="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-slate-600">
            <!-- Format Tag -->
            <span class="rounded-md bg-slate-100 px-2 py-0.5 text-[10px] font-mono font-bold uppercase tracking-wider text-slate-600 border border-slate-200/80">
              {{ formatBadge }}
            </span>

            <!-- Filename -->
            <span class="font-mono text-slate-500 text-[11px]">{{ document.filename }}</span>

            <template v-if="externalSystem">
              <span class="text-slate-300">·</span>
              <span class="font-medium text-slate-600 text-[11px]">{{ externalSystem }}</span>
            </template>

            <template v-if="document.parsed_summary?.page_count">
              <span class="text-slate-300">·</span>
              <span class="text-slate-500 text-[11px]">
                {{ document.parsed_summary.page_count }} {{ document.parsed_summary.page_count === 1 ? 'page' : 'pages' }}
              </span>
            </template>

            <span class="text-slate-300">·</span>

            <!-- Extraction confidence describes source recovery only. -->
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

      <!-- Metadata Strip -->
      <div class="mt-5 border-t border-slate-100 pt-4">
        <div class="grid grid-cols-2 gap-3 md:grid-cols-4 text-xs">
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
              {{ document.quotation?.commercial_terms?.currency || "USD" }}
              <span v-if="document.quotation?.commercial_terms?.incoterm" class="text-slate-600">
                · {{ document.quotation.commercial_terms.incoterm }}
              </span>
              <span v-if="document.quotation?.commercial_terms?.incoterm_named_place" class="text-slate-500 text-[11px]">
                ({{ document.quotation.commercial_terms.incoterm_named_place }})
              </span>
            </p>
            <p v-if="document.quotation?.commercial_terms?.incoterm_country" class="mt-1 text-[11px] text-slate-500">
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
  </div>
</template>
