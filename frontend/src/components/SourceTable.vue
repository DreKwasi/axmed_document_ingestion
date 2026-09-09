<script setup lang="ts">
/** Dashboard table listing all uploaded quotation sources and extraction statuses. */

import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import type { DocumentResponse } from "@/types";

// --- Section 1: Props & Emits ---

const props = defineProps<{
  documents: DocumentResponse[];
  busy: boolean;
}>();

const emit = defineEmits<{
  (event: "select", document: DocumentResponse): void;
  (event: "ingest"): void;
  (event: "delete", document: DocumentResponse): void;
  (event: "preview", document: DocumentResponse): void;
  (event: "export"): void;
  (event: "openHowItWorks"): void;
}>();

// --- Section 2: Peer Image Extraction Row Expansion ---

const allSourceRows = computed(() => props.documents.flatMap((document) => {
  const isImage = document.source_system === "image" || /\.(png|jpg|jpeg)$/i.test(document.filename);
  const attempts = document.image_extraction_attempts ?? [];
  if (isImage) {
    if (attempts.length >= 2) {
      return attempts.map((attempt) => ({
        ...document,
        source_result: attempt.approach,
        source_name: `${sourceName(document)} — ${attempt.approach === "ocr_assisted" ? "OCR-assisted" : "Direct vision"}`,
        extraction_confidence: attempt.extraction_confidence ?? document.extraction_confidence,
        mapping_confidence: attempt.mapping_confidence,
        status: attempt.status === "failed" ? "failed" : document.status,
        product_counts: { extracted: attempt.product_count, failed: 0 },
      }));
    }
    const ocrAttempt = attempts.find((a) => a.approach === "ocr_assisted");
    const visionAttempt = attempts.find((a) => a.approach === "vision_direct");
    return [
      {
        ...document,
        source_result: "ocr_assisted",
        source_name: `${sourceName(document)} — OCR-assisted`,
        extraction_confidence: ocrAttempt?.extraction_confidence ?? document.extraction_confidence,
        mapping_confidence: ocrAttempt?.mapping_confidence,
        product_counts: ocrAttempt
          ? { extracted: ocrAttempt.product_count, failed: 0 }
          : { extracted: 0, failed: 0 },
      },
      {
        ...document,
        source_result: "vision_direct",
        source_name: `${sourceName(document)} — Direct vision`,
        extraction_confidence: visionAttempt?.extraction_confidence ?? document.extraction_confidence,
        mapping_confidence: visionAttempt?.mapping_confidence,
        product_counts: visionAttempt
          ? { extracted: visionAttempt.product_count, failed: 0 }
          : { extracted: 0, failed: 0 },
      },
    ];
  }
  return [document];
}));

type StatusFilter = "all" | "preapproved" | "review" | "approved" | "rejected" | "failed" | "processing";

const statusFilter = ref<StatusFilter>("all");
const sourceRows = computed(() => (
  statusFilter.value === "all"
    ? allSourceRows.value
    : allSourceRows.value.filter((document) => statusKey(document) === statusFilter.value)
));

// --- Section 3: Tooltip Controls ---

const activeMappingTooltip = ref<string | null>(null);

function closeTooltips() {
  activeMappingTooltip.value = null;
}

function toggleMappingTooltip(documentId: string) {
  activeMappingTooltip.value = activeMappingTooltip.value === documentId ? null : documentId;
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

// --- Section 4: Display & Status Helpers ---

function sourceName(doc: DocumentResponse): string {
  if (doc.source_name) return doc.source_name;
  const supplier = doc.quotation?.supplier.name;
  const ref = doc.quotation?.quotation_reference;
  if (supplier && ref) return `${supplier} · ${ref}`;
  if (supplier) return `${supplier} quotation`;
  const filename = doc.filename.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").trim();
  return filename.replace(/\b\w/g, (c) => c.toUpperCase()) || "Untitled source";
}

function confidenceClass(band?: string | null): string {
  if (band === "High") return "text-ok";
  if (band === "Medium") return "text-alert";
  if (band === "Low") return "text-down";
  return "text-ink-3";
}

function productCounts(doc: DocumentResponse): { extracted: number; failed: number } {
  return doc.product_counts ?? {
    extracted: doc.quotation?.line_items.length ?? 0,
    failed: 0,
  };
}

function isApproved(doc: DocumentResponse): boolean {
  return doc.status === "approved" || doc.quotation?.review_status === "approved";
}

function isRejected(doc: DocumentResponse): boolean {
  return doc.status === "rejected" || doc.status === "auto_rejected" || doc.quotation?.review_status === "rejected";
}

function statusKey(doc: DocumentResponse): "approved" | "preapproved" | "review" | "rejected" | "failed" | "processing" {
  if (isApproved(doc)) return "approved";
  if (doc.status === "failed") return "failed";
  if (doc.status === "pre_approved" || doc.quotation?.review_status === "pre_approved") return "preapproved";
  if (isRejected(doc)) return "rejected";
  if (doc.status === "pending_review") return "review";
  return "processing";
}

function statusLabel(doc: DocumentResponse): string {
  if (doc.status === "failed") return "Extraction failed";
  if (doc.status === "auto_rejected") return "Material unusable";
  if (isRejected(doc)) return "Rejected";
  if (isApproved(doc)) return "Approved";
  const map = {
    approved: "Approved",
    preapproved: "Pre-approved",
    review: "Needs review",
    rejected: "Rejected",
    failed: "Extraction failed",
    processing: "Processing",
  };
  return map[statusKey(doc)];
}

function statusClasses(doc: DocumentResponse): string {
  const map = {
    approved: "bg-emerald-50 text-emerald-800 border-emerald-300",
    preapproved: "bg-sky-50 text-sky-800 border-sky-300",
    review: "bg-amber-50 text-amber-900 border-amber-300",
    rejected: "bg-rose-50 text-rose-800 border-rose-300",
    failed: "bg-rose-50 text-rose-800 border-rose-300",
    processing: "bg-surface-alt text-ink-3 border-rule",
  };
  return map[statusKey(doc)];
}

function formatBadge(filename: string, sourceSystem?: string | null): string {
  const lower = filename.toLowerCase();
  if (lower.endsWith(".pdf")) return "PDF";
  if (lower.endsWith(".json")) return "JSON";
  if (lower.endsWith(".eml")) return "EML";
  if (lower.endsWith(".png") || lower.endsWith(".jpg") || lower.endsWith(".jpeg")) return "IMG";
  return sourceSystem?.toUpperCase() || "DOC";
}

function mappingConfidenceExplanation(doc: DocumentResponse): string {
  const score = doc.mapping_confidence?.score;
  if (score == null) return "Mapping confidence is unavailable for this source.";
  const issueCount = doc.mapping_confidence?.issue_count ?? 0;
  return `This is the average confidence that extracted values were assigned to the correct schema fields: ${score}%. Mapping issues are counted separately: ${issueCount}.`;
}

function mappingConfidenceLabel(doc: DocumentResponse): string {
  if (doc.status === "failed") return "Not applicable";
  if (doc.mapping_confidence?.score != null) return `${doc.mapping_confidence.score}%`;
  return "—";
}
</script>

<template>
  <div class="space-y-4">
    <!-- Uploaded Sources Table Card -->
    <div class="overflow-hidden rounded-2xl border border-rule bg-surface shadow-xs">
      <div class="flex flex-wrap items-center justify-between gap-3 border-b border-rule px-4 py-3 sm:px-6 sm:py-4.5">
        <div>
          <h2 class="text-sm sm:text-base font-bold text-ink">Uploaded sources</h2>
          <p class="mt-0.5 text-xs text-ink-3">
            {{ documents.length }} total documents ·
            <template v-if="statusFilter === 'all'">{{ allSourceRows.length }} extraction results</template>
            <template v-else>{{ sourceRows.length }} of {{ allSourceRows.length }} extraction results</template>
            · Click any row to view extracted products and schema.
          </p>
        </div>
        <div class="flex items-center gap-2">
          <label class="sr-only" for="source-status-filter">Filter by status</label>
          <select
            id="source-status-filter"
            v-model="statusFilter"
            class="app-select text-xs"
            aria-label="Filter by status"
          >
            <option value="all">All statuses</option>
            <option value="preapproved">Pre-approved</option>
            <option value="review">Needs review</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
            <option value="failed">Extraction failed</option>
            <option value="processing">Processing</option>
          </select>
          <button
            type="button"
            class="rounded-lg border border-rule-dark bg-white px-3.5 py-2 text-xs font-semibold text-ink-2 transition hover:bg-surface-alt disabled:opacity-40"
            :disabled="!documents.length"
            @click="emit('export')"
          >
            Export CSV
          </button>
          <button
            type="button"
            class="rounded-lg border border-rule-dark bg-white px-3.5 py-2 text-xs font-semibold text-ink-2 transition hover:bg-surface-alt cursor-pointer shadow-2xs"
            @click="emit('openHowItWorks')"
          >
            How it works
          </button>
          <button
            type="button"
            class="rounded-lg bg-[#261c7a] px-3.5 py-2 text-xs font-semibold text-white transition hover:bg-[#1e155c] disabled:opacity-50 cursor-pointer"
            :disabled="busy"
            @click="emit('ingest')"
          >
            {{ busy ? "Ingesting…" : "Ingest source" }}
          </button>
        </div>
      </div>

      <div v-if="documents.length" class="overflow-x-auto">
        <table class="w-full min-w-[640px] text-left text-xs">
          <thead class="bg-surface-alt text-[10px] font-bold uppercase tracking-wider text-ink-2 border-b border-rule">
            <tr>
              <th class="px-4 py-3 sm:px-6 sm:py-3.5">Source</th>
              <th class="px-4 py-3.5">Extraction confidence</th>
              <th class="px-4 py-3.5">Mapping confidence</th>
              <th class="px-4 py-3.5">Products</th>
              <th class="px-4 py-3.5">Status</th>
              <th class="px-6 py-3.5 text-right">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-rule">
            <tr
              v-for="doc in sourceRows"
              :key="`${doc.id}:${doc.source_result ?? 'source'}`"
              class="group cursor-pointer transition hover:bg-surface-alt/70"
              @click="closeTooltips(); emit('select', doc)"
            >
              <!-- Source name and in-platform file preview -->
              <td class="px-6 py-4 align-top">
                <div class="flex items-start gap-3">
                  <span class="mt-0.5 inline-flex min-w-10 justify-center rounded-md border border-slate-200 bg-slate-50 px-1.5 py-1 text-[9px] font-medium tracking-[0.1em] text-slate-500 uppercase">
                    {{ formatBadge(doc.filename, doc.source_system) }}
                  </span>
                  <div class="min-w-0">
                    <button
                      type="button"
                      class="group block max-w-sm text-left text-[13px] font-medium leading-[1.45rem] text-slate-700 transition group-hover:text-axmed-primary sm:max-w-md cursor-pointer"
                      :title="sourceName(doc)"
                    >
                      <span class="block truncate max-w-sm sm:max-w-md">{{ sourceName(doc) }}</span>
                    </button>
                    <div class="flex items-center">
                      <button
                        type="button"
                        class="max-w-xs truncate text-left text-[11px] font-normal leading-[1.15rem] text-slate-400 transition hover:text-slate-600 hover:underline sm:max-w-md cursor-pointer"
                        :title="`Preview ${doc.filename}`"
                        @click.stop="emit('preview', doc)"
                      >
                        {{ doc.filename }}
                      </button>
                    </div>
                  </div>
                </div>
              </td>

              <td class="px-4 py-4 align-top">
                <span class="font-bold" :class="confidenceClass(doc.extraction_confidence?.band)">
                  {{ doc.extraction_confidence ? `${doc.extraction_confidence.score}%` : "—" }}
                </span>
                <span v-if="doc.extraction_confidence" class="block text-[10px] text-slate-500">
                  {{ doc.extraction_confidence.band }}
                </span>
              </td>

              <td class="px-4 py-4 align-top font-semibold">
                <span class="relative inline-flex" data-tooltip-container>
                  <button
                    type="button"
                    :class="confidenceClass(doc.mapping_confidence?.band)"
                    class="font-semibold"
                    :aria-expanded="activeMappingTooltip === doc.id"
                    :title="mappingConfidenceExplanation(doc)"
                    aria-label="Explain mapping confidence"
                    @click.stop="toggleMappingTooltip(doc.id)"
                  >
                    {{ mappingConfidenceLabel(doc) }}
                  </button>
                  <span
                    v-if="activeMappingTooltip === doc.id"
                    role="tooltip"
                    class="absolute right-0 top-6 z-50 w-72 rounded-lg border border-slate-200 bg-white p-3 text-[11px] font-normal leading-4 text-slate-700 shadow-lg"
                  >
                    {{ mappingConfidenceExplanation(doc) }}
                  </span>
                </span>
                <span
                  v-if="doc.mapping_confidence?.issue_count"
                  class="block text-[10px] font-semibold text-rose-600"
                >
                  {{ doc.mapping_confidence.issue_count }} {{ doc.mapping_confidence.issue_count === 1 ? "issue" : "issues" }} found
                </span>
                <span v-else-if="doc.mapping_confidence?.score != null" class="block text-[10px] text-slate-500">
                  {{ doc.status === "failed" ? "Not applicable" : "No issues found" }}
                </span>
              </td>

              <!-- Products -->
              <td class="px-4 py-4 align-top text-slate-700">
                <span class="font-bold text-slate-900">{{ productCounts(doc).extracted }}</span> extracted
              </td>

              <!-- Status -->
              <td class="px-4 py-4 align-top">
                <span
                  class="inline-flex items-center rounded-lg border px-2.5 py-1 text-[11px] font-bold tracking-wide uppercase"
                  :class="statusClasses(doc)"
                >
                  {{ statusLabel(doc) }}
                </span>
              </td>

              <!-- Open / destructive actions stay separate from the row click. -->
              <td class="px-6 py-4 align-top text-right">
                <div class="inline-flex items-center gap-1">
                  <button
                    type="button"
                    class="inline-flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 transition hover:bg-rose-50 hover:text-rose-700 disabled:cursor-not-allowed disabled:opacity-50 cursor-pointer"
                    :disabled="busy"
                    :aria-label="`Delete ${sourceName(doc)}`"
                    @click.stop="emit('delete', doc)"
                  >
                    <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M4 7h16M9 7V4h6v3m-8 0 1 13h8l1-13M10 11v5m4-5v5" />
                    </svg>
                  </button>
                  <button
                    type="button"
                    class="rounded-lg p-1.5 text-ink-3 group-hover:text-axmed-primary group-hover:translate-x-0.5 transition cursor-pointer"
                    :aria-label="`Open ${sourceName(doc)}`"
                  >
                    →
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="!sourceRows.length">
              <td colspan="6" class="px-6 py-12 text-center text-xs text-ink-3">
                No sources match this status.
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Clean Empty State -->
      <div v-else class="px-6 py-16 text-center">
        <div class="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-surface-alt text-ink-3 text-xl mb-3 border border-rule">
          📄
        </div>
        <p class="text-sm font-bold text-ink">No sources yet.</p>
        <p class="mt-1 text-xs text-ink-3 max-w-sm mx-auto">
          Ingest a PDF, email, image, or JSON offer to begin review.
        </p>
      </div>
    </div>
  </div>
</template>
