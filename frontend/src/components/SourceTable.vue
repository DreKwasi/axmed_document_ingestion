<script setup lang="ts">
import { ref } from "vue";
import type { DocumentResponse } from "@/types";
import { sourceDocumentUrl } from "@/api";

defineProps<{
  documents: DocumentResponse[];
  busy: boolean;
}>();

const emit = defineEmits<{
  (event: "select", document: DocumentResponse): void;
  (event: "ingest"): void;
  (event: "delete", document: DocumentResponse): void;
}>();

const activeMappingTooltip = ref<string | null>(null);

function sourceName(doc: DocumentResponse) {
  if (doc.source_name) return doc.source_name;
  const supplier = doc.quotation?.supplier.name;
  const ref = doc.quotation?.quotation_reference;
  if (supplier && ref) return `${supplier} · ${ref}`;
  if (supplier) return `${supplier} quotation`;
  const filename = doc.filename.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").trim();
  return filename.replace(/\b\w/g, (c) => c.toUpperCase()) || "Untitled source";
}

function confidenceClass(band?: string | null) {
  if (band === "High") return "text-emerald-700";
  if (band === "Medium") return "text-amber-700";
  if (band === "Low") return "text-rose-700";
  return "text-slate-400";
}

function productCounts(doc: DocumentResponse) {
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

function statusLabel(doc: DocumentResponse) {
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

function statusClasses(doc: DocumentResponse) {
  const map = {
    ready: "bg-emerald-50 text-emerald-700 border-emerald-200",
    review: "bg-teal-50 text-teal-700 border-teal-200",
    needs_attention: "bg-rose-50 text-rose-700 border-rose-200",
    processing: "bg-slate-100 text-slate-600 border-slate-200",
  };
  return map[statusKey(doc)];
}

function formatBadge(filename: string, sourceSystem?: string | null) {
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

function toggleMappingTooltip(documentId: string) {
  activeMappingTooltip.value = activeMappingTooltip.value === documentId ? null : documentId;
}

</script>

<template>
  <div class="space-y-4">
    <!-- Uploaded Sources Table Card -->
    <div class="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xs">
      <div class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-6 py-4.5">
        <div>
          <h2 class="text-base font-bold text-slate-900">Uploaded sources</h2>
          <p class="mt-0.5 text-xs text-slate-500">
            {{ documents.length }} total documents · Click any row to view extracted products and schema.
          </p>
        </div>
      </div>

      <div v-if="documents.length" class="overflow-x-auto">
        <table class="w-full text-left text-xs">
          <thead class="bg-slate-50 text-[10px] font-bold uppercase tracking-wider text-slate-500 border-b border-slate-100">
            <tr>
              <th class="px-6 py-3.5">Source</th>
              <th class="px-4 py-3.5">Extraction confidence</th>
              <th class="px-4 py-3.5">Mapping confidence</th>
              <th class="px-4 py-3.5">Products</th>
              <th class="px-4 py-3.5">Status</th>
              <th class="px-6 py-3.5 text-right">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            <tr
              v-for="doc in documents"
              :key="doc.id"
              class="group cursor-pointer transition hover:bg-slate-50/80"
              @click="emit('select', doc)"
            >
              <!-- Source Name, File, Download -->
              <td class="px-6 py-4 align-top">
                <div class="flex items-start gap-2.5">
                  <span class="mt-0.5 rounded-md bg-slate-100 px-2 py-0.5 text-[10px] font-bold tracking-wider text-slate-600 uppercase border border-slate-200">
                    {{ formatBadge(doc.filename, doc.source_system) }}
                  </span>
                  <div>
                    <button
                      type="button"
                      class="group block text-left font-bold text-slate-900 group-hover:text-emerald-800 transition"
                      :title="sourceName(doc)"
                    >
                      <span class="block truncate max-w-sm sm:max-w-md">{{ sourceName(doc) }}</span>
                    </button>
                    <div class="mt-1 flex items-center gap-2 text-[11px]">
                      <a
                        class="font-semibold text-emerald-700 hover:text-emerald-900 hover:underline transition"
                        :href="sourceDocumentUrl(doc.id)"
                        :download="doc.filename"
                        @click.stop
                      >
                        Download file
                      </a>
                      <span class="text-slate-300">·</span>
                      <span class="text-slate-400 font-mono text-[10px] truncate max-w-xs">{{ doc.filename }}</span>
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
                <span class="relative inline-flex">
                  <button
                    type="button"
                    :class="confidenceClass(doc.mapping_confidence?.band)"
                    class="font-semibold"
                    :aria-expanded="activeMappingTooltip === doc.id"
                    :title="mappingConfidenceExplanation(doc)"
                    aria-label="Explain mapping confidence"
                    @click.stop="toggleMappingTooltip(doc.id)"
                  >
                    {{ doc.mapping_confidence?.score != null ? `${doc.mapping_confidence.score}%` : "—" }}
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
                <span v-else class="block text-[10px] text-slate-500">
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
                    class="rounded-lg px-2 py-1.5 text-[11px] font-semibold text-rose-600 hover:bg-rose-50 hover:text-rose-700 transition disabled:cursor-not-allowed disabled:opacity-50"
                    :disabled="busy"
                    :aria-label="`Delete ${sourceName(doc)}`"
                    @click.stop="emit('delete', doc)"
                  >
                    Delete
                  </button>
                  <button
                    type="button"
                    class="rounded-lg p-1.5 text-slate-400 group-hover:text-emerald-700 group-hover:translate-x-0.5 transition"
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
        <div class="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 text-slate-400 text-xl mb-3">
          📄
        </div>
        <p class="text-sm font-bold text-slate-800">No sources yet.</p>
        <p class="mt-1 text-xs text-slate-500 max-w-sm mx-auto">
          Ingest a PDF, email, image, or JSON offer to begin review.
        </p>
        <button
          type="button"
          class="mt-4 rounded-xl bg-emerald-800 px-4 py-2 text-xs font-bold text-white hover:bg-emerald-900 transition shadow-xs"
          :disabled="busy"
          @click="emit('ingest')"
        >
          Ingest source
        </button>
      </div>
    </div>
  </div>
</template>
