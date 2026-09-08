<script setup lang="ts">
/** Dashboard table listing all uploaded quotation sources and extraction statuses. */

import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import type { DocumentResponse } from "@/types";
import { sourceDocumentUrl } from "@/api";

// --- Section 1: Props & Emits ---

const props = defineProps<{
  documents: DocumentResponse[];
  busy: boolean;
}>();

const emit = defineEmits<{
  (event: "select", document: DocumentResponse): void;
  (event: "ingest"): void;
  (event: "delete", document: DocumentResponse): void;
}>();

// --- Section 2: Peer Image Extraction Row Expansion ---

const sourceRows = computed(() => props.documents.flatMap((document) => {
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
        product_counts: { extracted: attempt.product_count, failed: attempt.status === "failed" ? 1 : 0 },
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
          ? { extracted: ocrAttempt.product_count, failed: ocrAttempt.status === "failed" ? 1 : 0 }
          : { extracted: 0, failed: 0 },
      },
      {
        ...document,
        source_result: "vision_direct",
        source_name: `${sourceName(document)} — Direct vision`,
        extraction_confidence: visionAttempt?.extraction_confidence ?? document.extraction_confidence,
        mapping_confidence: visionAttempt?.mapping_confidence,
        product_counts: visionAttempt
          ? { extracted: visionAttempt.product_count, failed: visionAttempt.status === "failed" ? 1 : 0 }
          : { extracted: 0, failed: 0 },
      },
    ];
  }
  return [document];
}));

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

function statusKey(doc: DocumentResponse): "ready" | "review" | "needs_attention" | "processing" {
  if (doc.quotation?.review_status === "approved") return "ready";
  if (["failed", "rejected"].includes(doc.status) || doc.quotation?.review_status === "rejected") {
    return "needs_attention";
  }
  if (doc.status === "approved") return "ready";
  if (doc.status === "pending_review") return "review";
  return "processing";
}

function statusLabel(doc: DocumentResponse): string {
  if (doc.status === "failed") return "Extraction failed";
  if (doc.status === "rejected" || doc.quotation?.review_status === "rejected") return "Rejected";
  if (doc.status === "pending_review" && doc.quotation?.has_corrections) return "Review corrected";
  const map = {
    ready: "Ready",
    review: "Pending review",
    needs_attention: "Needs attention",
    processing: "Processing",
  };
  return map[statusKey(doc)];
}

function statusClasses(doc: DocumentResponse): string {
  const map = {
    ready: "bg-ok-bg text-ok border-[#a6f4c5]",
    review: "bg-axmed-primary-tint text-axmed-primary border-[#d0d5dd]",
    needs_attention: "bg-down-bg text-down border-[#fecdca]",
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
  if (score == null) return "No mapped fields are available to assess.";
  const issueCount = doc.mapping_confidence?.issue_count ?? 0;
  return `This is the average confidence that extracted values were assigned to the correct schema fields: ${score}%. Mapping issues are counted separately: ${issueCount}.`;
}

function mappingConfidenceLabel(doc: DocumentResponse): string {
  if (doc.status === "failed") return "Not applicable";
  if (doc.mapping_confidence?.score != null) return `${doc.mapping_confidence.score}%`;
  if (doc.mapping_confidence?.issue_count === 0) return "No issues";
  return "Pending";
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
            {{ documents.length }} total documents · {{ sourceRows.length }} extraction results · Click any row to view extracted products and schema.
          </p>
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
              <!-- Source Name, File, Download -->
              <td class="px-6 py-4 align-top">
                <div class="flex items-start gap-2.5">
                  <span class="mt-0.5 rounded-md bg-surface-alt px-2 py-0.5 text-[10px] font-bold tracking-wider text-ink-2 uppercase border border-rule">
                    {{ formatBadge(doc.filename, doc.source_system) }}
                  </span>
                  <div>
                    <button
                      type="button"
                      class="group block text-left font-bold text-ink group-hover:text-axmed-primary transition cursor-pointer"
                      :title="sourceName(doc)"
                    >
                      <span class="block truncate max-w-sm sm:max-w-md">{{ sourceName(doc) }}</span>
                    </button>
                    <div class="mt-1 flex items-center text-[11px]">
                      <a
                        class="font-mono text-[10px] text-ink-3 hover:text-axmed-primary hover:underline transition truncate max-w-xs sm:max-w-md cursor-pointer"
                        :href="sourceDocumentUrl(doc.id)"
                        :download="doc.filename"
                        :title="`Download ${doc.filename}`"
                        @click.stop
                      >
                        {{ doc.filename }}
                      </a>
                    </div>
                    <p v-if="doc.notes?.[0]" class="mt-1 text-[11px] text-slate-500 line-clamp-1">
                      {{ doc.notes[0] }}
                    </p>
                  </div>
                </div>
              </td>

              <td class="px-4 py-4 align-top">
                <span class="font-bold" :class="confidenceClass(doc.extraction_confidence?.band)">
                  {{ doc.extraction_confidence ? `${doc.extraction_confidence.score}%` : "—" }}
                </span>
                <span class="block text-[10px] text-slate-500">
                  {{ doc.extraction_confidence?.band || (doc.status === "failed" ? "Failed" : "Pending") }}
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
                <span v-if="productCounts(doc).failed" class="block text-[10px] font-semibold text-rose-600 mt-0.5">
                  {{ productCounts(doc).failed }} failed
                </span>
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
                    class="rounded-lg px-2 py-1.5 text-[11px] font-semibold text-down hover:bg-down-bg transition disabled:cursor-not-allowed disabled:opacity-50 cursor-pointer"
                    :disabled="busy"
                    :aria-label="`Delete ${sourceName(doc)}`"
                    @click.stop="emit('delete', doc)"
                  >
                    Delete
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
        <button
          type="button"
          class="mt-4 rounded-xl bg-[#261c7a] px-4 py-2 text-xs font-bold text-white hover:bg-[#1e155c] active:bg-[#150f42] transition shadow-xs cursor-pointer"
          :disabled="busy"
          @click="emit('ingest')"
        >
          Ingest source
        </button>
      </div>
    </div>
  </div>
</template>
