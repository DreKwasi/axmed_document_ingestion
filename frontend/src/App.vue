<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import {
  deleteDocument as apiDeleteDocument,
  eventStreamUrl,
  fetchDocument,
  fetchDocuments,
  fetchEvents,
  openImageExtractionForReview,
  reviewDocument,
  reextractDocument,
  uploadDocuments,
} from "@/api";
import type { DocumentResponse, ProcessingEvent } from "@/types";
import { documentsToCsv } from "@/exportCsv";

import ProductDetailDrawer from "./components/ProductDetailDrawer.vue";
import ProductTable from "./components/ProductTable.vue";
import ReviewModal from "./components/ReviewModal.vue";
import SourceDetailHeader from "./components/SourceDetailHeader.vue";
import SourceTable from "./components/SourceTable.vue";

const documents = ref<DocumentResponse[]>([]);
const selectedDocumentId = ref<string | null>(null);
const selectedLineIndex = ref(0);
const isDrawerOpen = ref(false);
const isReviewModalOpen = ref(false);
const busy = ref(false);
const errorMessage = ref("");
const fileInput = ref<HTMLInputElement | null>(null);
const extractionActivity = ref<Record<string, ProcessingEvent[]>>({});
const eventSources = new Map<string, EventSource>();

const selectedDocument = computed(() =>
  documents.value.find((document) => document.id === selectedDocumentId.value) ?? null
);

const selectedLine = computed(() =>
  selectedDocument.value?.quotation?.line_items[selectedLineIndex.value] ?? null
);

function openIngest() {
  fileInput.value?.click();
}

function exportAllData() {
  const csv = documentsToCsv(documents.value);
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const link = window.document.createElement("a");
  link.href = url;
  link.download = "axmed-export.csv";
  link.click();
  URL.revokeObjectURL(url);
}

function openDocument(document: DocumentResponse) {
  selectedDocumentId.value = document.id;
  selectedLineIndex.value = 0;
  isDrawerOpen.value = false;
  void loadActivity(document.id);
}

function closeDocument() {
  selectedDocumentId.value = null;
  isDrawerOpen.value = false;
  isReviewModalOpen.value = false;
}

async function removeDocument(document: DocumentResponse) {
  const sourceName = document.source_name || document.filename;
  if (!window.confirm(`Delete ${sourceName}? This removes the uploaded file and all extracted data.`)) return;

  busy.value = true;
  errorMessage.value = "";
  try {
    await apiDeleteDocument(document.id);
    documents.value = documents.value.filter((item) => item.id !== document.id);
    eventSources.get(document.id)?.close();
    eventSources.delete(document.id);
    delete extractionActivity.value[document.id];
    if (selectedDocumentId.value === document.id) closeDocument();
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "Source deletion failed.";
  } finally {
    busy.value = false;
  }
}

async function loadDocuments() {
  documents.value = await fetchDocuments();
}

async function loadActivity(documentId: string) {
  try {
    extractionActivity.value = {
      ...extractionActivity.value,
      [documentId]: await fetchEvents(documentId),
    };
  } catch {
    // Activity is supplemental to the source review
  }
}

function addActivity(documentId: string, event: ProcessingEvent) {
  const current = extractionActivity.value[documentId] ?? [];
  if (current.some((existing) => existing.id === event.id)) return;
  extractionActivity.value = {
    ...extractionActivity.value,
    [documentId]: [...current, event].sort((left, right) => left.id - right.id),
  };
}

function replaceDocument(nextDocument: DocumentResponse) {
  documents.value = documents.value.map((doc) => (doc.id === nextDocument.id ? nextDocument : doc));
}

function watchDocument(documentId: string) {
  void loadActivity(documentId);
  if (typeof EventSource === "undefined" || eventSources.has(documentId)) return;
  const source = new EventSource(eventStreamUrl(documentId));
  source.addEventListener("processing", (rawEvent) => {
    const data = rawEvent ? (rawEvent as MessageEvent<string>).data : "";
    if (data) {
      try {
        addActivity(documentId, JSON.parse(data) as ProcessingEvent);
      } catch {
        // Fall back to document refresh below
      }
    }
    void fetchDocument(documentId).then(replaceDocument).catch(() => undefined);
  });
  eventSources.set(documentId, source);
}

async function chooseFile(event: Event) {
  const input = event.target as HTMLInputElement;
  const files = Array.from(input.files ?? []);
  if (!files.length) return;
  busy.value = true;
  errorMessage.value = "";
  try {
    const uploaded = await uploadDocuments(files);
    const uploadedIds = new Set(uploaded.map((document) => document.id));
    documents.value = [...uploaded, ...documents.value.filter((document) => !uploadedIds.has(document.id))];
    uploaded.forEach((document) => watchDocument(document.id));
    if (uploaded.length === 1) openDocument(uploaded[0]);
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "Upload failed.";
  } finally {
    busy.value = false;
    input.value = "";
  }
}

async function reextract(document: DocumentResponse) {
  busy.value = true;
  errorMessage.value = "";
  try {
    const updated = await reextractDocument(document.id);
    replaceDocument(updated);
    isDrawerOpen.value = false;
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "Re-extraction failed.";
  } finally {
    busy.value = false;
  }
}

async function openCandidateForReview(approach: string) {
  const doc = selectedDocument.value;
  if (!doc) return;
  busy.value = true;
  errorMessage.value = "";
  try {
    replaceDocument(await openImageExtractionForReview(doc.id, approach));
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "Could not open this extraction for review.";
  } finally {
    busy.value = false;
  }
}

async function handleSaveCorrection(payload: { fieldPath: string; value: unknown; lineIndex: number }) {
  const doc = selectedDocument.value;
  if (!doc?.quotation) return;
  busy.value = true;
  errorMessage.value = "";
  try {
    replaceDocument(
      await reviewDocument(doc.id, "correct", {
        request_id: `${doc.id}:${doc.quotation.revision}:correct:${payload.lineIndex}`,
        expected_revision: doc.quotation.revision,
        patches: [{ path: payload.fieldPath, value: payload.value }],
      })
    );
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "Correction failed.";
  } finally {
    busy.value = false;
  }
}

async function handleApprove(note?: string) {
  const doc = selectedDocument.value;
  if (!doc?.quotation) return;
  busy.value = true;
  errorMessage.value = "";
  try {
    replaceDocument(
      await reviewDocument(doc.id, "approve", {
        request_id: `${doc.id}:${doc.quotation.revision}:approve`,
        expected_revision: doc.quotation.revision,
        note,
      })
    );
    isReviewModalOpen.value = false;
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "Approval failed.";
  } finally {
    busy.value = false;
  }
}

async function handleReject(payload: { reason: string; note?: string }) {
  const doc = selectedDocument.value;
  if (!doc?.quotation) return;
  busy.value = true;
  errorMessage.value = "";
  try {
    replaceDocument(
      await reviewDocument(doc.id, "reject", {
        request_id: `${doc.id}:${doc.quotation.revision}:reject`,
        expected_revision: doc.quotation.revision,
        note: payload.note,
        rejection_reason: payload.reason,
      })
    );
    isReviewModalOpen.value = false;
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "Rejection failed.";
  } finally {
    busy.value = false;
  }
}


function currentExtractionEvent(doc: DocumentResponse | null): ProcessingEvent | null {
  if (!doc) return null;
  const events = extractionActivity.value[doc.id] ?? [];
  return events.length ? events[events.length - 1] : null;
}

function isExtractionOngoing(doc: DocumentResponse | null): boolean {
  if (!doc) return false;
  const latest = currentExtractionEvent(doc);
  if (latest) {
    const phaseLower = (latest.phase || "").toLowerCase();
    const stageLower = (latest.stage || "").toLowerCase();
    if (phaseLower === "complete" || stageLower.endsWith("_completed") || ["image_extractions_ready_for_comparison", "image_extraction_opened_for_review"].includes(stageLower)) return false;
    if (phaseLower === "needs attention" || stageLower.endsWith("_failed")) return false;
    return true;
  }
  if (["failed", "rejected"].includes(doc.status)) return false;
  if (["processing", "queued", "needs_semantic_extraction"].includes(doc.status)) return true;
  return false;
}

onMounted(() => loadDocuments().catch(() => undefined));
onBeforeUnmount(() => eventSources.forEach((source) => source.close()));
</script>

<template>
  <div class="min-h-screen bg-slate-50 text-slate-800 font-sans antialiased">
    <!-- Clean Minimal Header -->
    <header class="border-b border-slate-200 bg-white sticky top-0 z-30">
      <div class="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <div class="flex items-center gap-3">
          <span class="text-base font-black tracking-widest text-emerald-900 uppercase">
            AXMED
          </span>
          <span class="h-4 w-px bg-slate-200"></span>
          <span class="text-xs font-semibold text-slate-500">Document Intelligence</span>
        </div>

        <!-- Hidden input for file ingestion -->
        <input
          ref="fileInput"
          class="sr-only"
          type="file"
          accept="application/json,.json,message/rfc822,.eml,application/pdf,.pdf,image/png,.png,image/jpeg,.jpg,.jpeg"
          multiple
          @change="chooseFile"
        />
      </div>
    </header>

    <!-- Main Container -->
    <main class="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8 space-y-6">
      <!-- Error Message Banner -->
      <p
        v-if="errorMessage"
        class="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-xs font-semibold text-rose-700"
        role="alert"
      >
        {{ errorMessage }}
      </p>

      <!-- VIEW 1: HOME PAGE (No source selected) -->
      <div v-if="!selectedDocument" class="space-y-6">
        <!-- Home Header -->
        <section class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-slate-200 pb-6">
          <div>
            <h1 class="text-3xl font-extrabold tracking-tight text-slate-900 sm:text-4xl">Home</h1>
            <p class="mt-1 text-xs text-slate-500">
              Review uploaded supplier sources and open any source for its product breakdown.
            </p>
          </div>
          <div class="flex w-full shrink-0 gap-2 sm:w-auto">
            <button
              type="button"
              class="flex-1 rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-xs font-bold text-slate-700 shadow-xs hover:bg-slate-50 transition focus:outline-none disabled:opacity-50 sm:flex-none"
              :disabled="!documents.length"
              @click="exportAllData"
            >
              Export CSV
            </button>
            <button
              type="button"
              class="flex-1 rounded-xl bg-[#123b37] px-4 py-2.5 text-xs font-bold text-white shadow-xs hover:bg-emerald-950 transition focus:outline-none sm:flex-none disabled:opacity-50"
              :disabled="busy"
              @click="openIngest"
            >
              {{ busy ? "Ingesting…" : "Ingest source" }}
            </button>
          </div>
        </section>

        <!-- Uploaded Sources Table -->
        <SourceTable
          :documents="documents"
          :busy="busy"
          @select="openDocument"
          @ingest="openIngest"
          @delete="removeDocument"
        />
      </div>

      <!-- VIEW 2: SOURCE DETAIL PAGE -->
      <div v-else class="space-y-6">
        <!-- Source Detail Header & Schema Strip -->
        <SourceDetailHeader
          :document="selectedDocument"
          :busy="busy"
          @back="closeDocument"
          @open-review="isReviewModalOpen = true"
          @reextract="reextract(selectedDocument)"
        />

        <!-- Active Extraction Status (only shown while extraction is actively ongoing) -->
        <div
          v-if="isExtractionOngoing(selectedDocument)"
          class="flex items-center justify-between gap-3 rounded-xl border border-teal-200/80 bg-teal-50/70 px-4 py-3 text-xs shadow-2xs"
        >
          <div class="flex items-center gap-2.5 min-w-0">
            <span class="relative flex h-2.5 w-2.5 shrink-0">
              <span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-teal-400 opacity-75"></span>
              <span class="relative inline-flex h-2.5 w-2.5 rounded-full bg-teal-600"></span>
            </span>
            <div class="truncate">
              <span class="font-bold text-teal-950">
                {{ currentExtractionEvent(selectedDocument)?.phase || "Extracting" }}:
              </span>
              <span class="ml-1.5 text-teal-800">
                {{ currentExtractionEvent(selectedDocument)?.message || "Extracting quotation and line items…" }}
              </span>
            </div>
          </div>
          <div class="flex items-center gap-1.5 text-[11px] font-semibold text-teal-700 shrink-0">
            <svg class="h-3.5 w-3.5 animate-spin text-teal-600" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
            </svg>
            <span>In progress</span>
          </div>
        </div>

        <!-- Extracted Products Table -->
        <section v-if="selectedDocument.quotation">
          <ProductTable
            :line-items="selectedDocument.quotation.line_items"
            :mapping-issues="selectedDocument.mapping_issues ?? []"
            :field-reviews="selectedDocument.quotation.field_reviews"
            :selected-index="selectedLineIndex"
            @select-line="(idx) => { selectedLineIndex = idx; isDrawerOpen = true; }"
          />
        </section>

        <section
          v-else-if="selectedDocument.image_extraction_attempts?.length"
          class="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xs"
        >
          <div class="border-b border-slate-100 px-6 py-5">
            <h2 class="text-base font-bold text-slate-900">Compare image extractions</h2>
            <p class="mt-1 text-xs text-slate-500">
              These are two independent readings of the same source. Neither has been selected automatically.
            </p>
          </div>
          <div class="grid gap-4 p-5 lg:grid-cols-2">
            <article
              v-for="attempt in selectedDocument.image_extraction_attempts"
              :key="attempt.approach"
              class="rounded-xl border border-slate-200 p-4"
            >
              <div class="flex items-start justify-between gap-3">
                <div>
                  <h3 class="font-bold text-slate-900">
                    {{ attempt.approach === "ocr_assisted" ? "OCR-assisted extraction" : "Direct image extraction" }}
                  </h3>
                  <p class="mt-1 text-xs text-slate-500">
                    {{ attempt.status === "completed" ? `${attempt.product_count} extracted products` : attempt.failure_reason || "Extraction did not complete." }}
                  </p>
                </div>
                <button
                  v-if="attempt.status === 'completed' && attempt.result?.line_items.length"
                  type="button"
                  class="rounded-lg bg-emerald-800 px-3 py-1.5 text-xs font-bold text-white hover:bg-emerald-900 disabled:opacity-50"
                  :disabled="busy"
                  @click="openCandidateForReview(attempt.approach)"
                >
                  Review this extraction
                </button>
              </div>
              <dl v-if="attempt.result" class="mt-4 space-y-2 text-xs">
                <div class="flex justify-between gap-3"><dt class="text-slate-500">Supplier</dt><dd class="font-semibold text-slate-800 text-right">{{ attempt.result.supplier.name || "—" }}</dd></div>
                <div class="flex justify-between gap-3"><dt class="text-slate-500">Quotation reference</dt><dd class="font-semibold text-slate-800 text-right">{{ attempt.result.quotation_reference || "—" }}</dd></div>
              </dl>
              <ul v-if="attempt.result?.line_items.length" class="mt-4 divide-y divide-slate-100 border-t border-slate-100 text-xs">
                <li v-for="(item, index) in attempt.result.line_items" :key="item.source_key || index" class="flex justify-between gap-3 py-2">
                  <span class="font-semibold text-slate-800">{{ item.product.trade_name || item.product.inn.join(" · ") || "Unnamed product" }}</span>
                  <span class="text-slate-500">{{ item.product.dosage_form || "—" }}</span>
                </li>
              </ul>
            </article>
          </div>
        </section>

        <!-- Product Details Drawer / Inspector -->
        <ProductDetailDrawer
          :is-open="isDrawerOpen"
          :document="selectedDocument"
          :line-item="selectedLine"
          :line-index="selectedLineIndex"
          :busy="busy"
          @close="isDrawerOpen = false"
          @save-correction="handleSaveCorrection"
        />

        <!-- Review Decision Modal (Dialog) -->
        <ReviewModal
          :is-open="isReviewModalOpen"
          :document="selectedDocument"
          :busy="busy"
          @close="isReviewModalOpen = false"
          @approve="handleApprove"
          @reject="handleReject"
        />
      </div>
    </main>
  </div>
</template>
