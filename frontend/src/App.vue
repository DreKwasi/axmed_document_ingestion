<script setup lang="ts">
/** Root application coordinator managing document intake, inspection, and review decisions. */

import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

import {
  deleteDocument as apiDeleteDocument,
  eventStreamUrl,
  exportDocumentsUrl,
  fetchDocument,
  fetchDocuments,
  fetchEvents,
  openImageExtractionForReview,
  reviewDocument,
  reextractDocument,
  sourceDocumentUrl,
  uploadDocuments,
} from "@/api";
import type { DocumentResponse, ProcessingEvent } from "@/types";

import AxmedLogo from "./components/AxmedLogo.vue";
import ProductDetailDrawer from "./components/ProductDetailDrawer.vue";
import ProductTable from "./components/ProductTable.vue";
import ReviewModal from "./components/ReviewModal.vue";
import SourceDetailHeader from "./components/SourceDetailHeader.vue";
import SourcePreviewModal from "./components/SourcePreviewModal.vue";
import SourceTable from "./components/SourceTable.vue";

// --- Section 1: Reactive State & Selection ---

interface ToastNotification {
  show: boolean;
  title: string;
  message: string;
  type: "success" | "info" | "error";
}

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
const selectedApproach = ref<string | null>(null);
const previewDocument = ref<DocumentResponse | null>(null);

const toast = ref<ToastNotification>({
  show: false,
  title: "",
  message: "",
  type: "success",
});
let toastTimer: ReturnType<typeof setTimeout> | null = null;

function showToast(title: string, message: string, type: "success" | "info" | "error" = "success") {
  if (toastTimer) {
    clearTimeout(toastTimer);
    toastTimer = null;
  }
  toast.value = { show: true, title, message, type };
  toastTimer = setTimeout(() => {
    toast.value.show = false;
  }, 4000);
}

function dismissToast() {
  if (toastTimer) {
    clearTimeout(toastTimer);
    toastTimer = null;
  }
  toast.value.show = false;
}

// --- Section 2: Computed Getters ---

const selectedDocument = computed(() =>
  documents.value.find((document) => document.id === selectedDocumentId.value) ?? null
);

const selectedLine = computed(() =>
  selectedDocument.value?.quotation?.line_items[selectedLineIndex.value] ?? null
);

// --- Section 3: Ingestion & Document Actions ---

function openIngest() {
  fileInput.value?.click();
}

function exportAllData() {
  const link = window.document.createElement("a");
  link.href = exportDocumentsUrl();
  link.download = "axmed-export.csv";
  link.click();
}

type HistoryMode = "push" | "replace" | "none";

function writeSourceUrl(document: (DocumentResponse & { source_result?: string }) | null, mode: Exclude<HistoryMode, "none">) {
  const url = new URL(window.location.href);
  if (document) {
    url.searchParams.set("source", document.id);
    if (document.source_result) url.searchParams.set("approach", document.source_result);
    else url.searchParams.delete("approach");
  } else {
    url.searchParams.delete("source");
    url.searchParams.delete("approach");
  }
  window.history[`${mode}State`]({}, "", `${url.pathname}${url.search}${url.hash}`);
}

function openDocument(document: DocumentResponse & { source_result?: string }, historyMode: HistoryMode = "push") {
  selectedDocumentId.value = document.id;
  selectedApproach.value = document.source_result ?? null;
  selectedLineIndex.value = 0;
  isDrawerOpen.value = false;
  if (historyMode !== "none") writeSourceUrl(document, historyMode);
  void loadActivity(document.id);
}

function closeDocument(historyMode: HistoryMode = "push") {
  selectedDocumentId.value = null;
  selectedApproach.value = null;
  isDrawerOpen.value = false;
  isReviewModalOpen.value = false;
  if (historyMode !== "none") writeSourceUrl(null, historyMode);
}

function restoreViewFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const documentId = params.get("source");
  const document = documents.value.find((item) => item.id === documentId);
  if (!document) {
    closeDocument("none");
    return;
  }
  openDocument({ ...document, source_result: params.get("approach") ?? undefined }, "none");
}

function openSourcePreview(document: DocumentResponse) {
  previewDocument.value = document;
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
    const isImageUpload = uploaded.some(
      (doc) => doc.source_system === "image" || /\.(png|jpg|jpeg)$/i.test(doc.filename)
    );
    if (uploaded.length === 1 && !isImageUpload) {
      void openDocument(uploaded[0]);
    }
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

// --- Section 4: Real-Time Event Streaming (SSE) ---

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

// --- Section 5: Human Review & Peer Extractions ---

async function openCandidateForReview(approach: string) {
  const doc = selectedDocument.value;
  if (!doc) return;
  selectedApproach.value = approach;
  writeSourceUrl({ ...doc, source_result: approach }, "replace");

  const attempt = doc.image_extraction_attempts?.find((a) => a.approach === approach);
  if (attempt && attempt.status !== "completed") {
    // If the attempt is failed or not completed, do not make the review promotion API request.
    return;
  }

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

watch(
  () => [
    selectedDocument.value?.id,
    selectedDocument.value?.image_extraction_attempts?.length,
    selectedDocument.value?.quotation,
  ] as const,
  ([, attemptsLength, quotation]) => {
    const doc = selectedDocument.value;
    if (doc && !quotation && (attemptsLength ?? 0) > 0) {
      const completedAttempt =
        (selectedApproach.value && doc.image_extraction_attempts?.find((a) => a.approach === selectedApproach.value)?.status === "completed")
          ? selectedApproach.value
          : doc.image_extraction_attempts?.find((a) => a.status === "completed")?.approach;
      if (completedAttempt) {
        void openCandidateForReview(completedAttempt);
      }
    }
  }
);

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
    showToast("Correction Saved", "Field updated successfully.", "success");
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
    showToast("Source Approved", "Quotation approved and marked ready for commercial export.", "success");
    closeDocument();
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
    showToast("Source Rejected", `Quotation marked as rejected (${payload.reason}).`, "info");
    closeDocument();
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "Rejection failed.";
  } finally {
    busy.value = false;
  }
}

// --- Section 6: Lifecycle Hooks ---

onMounted(async () => {
  await loadDocuments().catch(() => undefined);
  restoreViewFromUrl();
  window.addEventListener("popstate", restoreViewFromUrl);
});
onBeforeUnmount(() => {
  if (toastTimer) clearTimeout(toastTimer);
  window.removeEventListener("popstate", restoreViewFromUrl);
  eventSources.forEach((source) => source.close());
});
</script>

<template>
  <div class="min-h-screen bg-slate-50 text-slate-800 font-sans antialiased">
    <!-- Toast Notification (Fixed Position, Smooth Floating Pill) -->
    <Transition
      enter-active-class="transition duration-300 ease-out"
      enter-from-class="transform -translate-y-2 opacity-0 sm:translate-y-0 sm:translate-x-4"
      enter-to-class="transform translate-y-0 opacity-100 sm:translate-x-0"
      leave-active-class="transition duration-200 ease-in"
      leave-from-class="transform opacity-100"
      leave-to-class="transform opacity-0 scale-95"
    >
      <div
        v-if="toast.show"
        class="fixed top-5 right-5 z-50 flex max-w-sm w-full items-start gap-3 rounded-2xl border p-4 shadow-xl backdrop-blur-md transition-all sm:max-w-md"
        :class="{
          'border-emerald-200 bg-white/95 text-emerald-950 shadow-emerald-900/10': toast.type === 'success',
          'border-blue-200 bg-white/95 text-blue-950 shadow-blue-900/10': toast.type === 'info',
          'border-rose-200 bg-white/95 text-rose-950 shadow-rose-900/10': toast.type === 'error',
        }"
        role="status"
        aria-live="polite"
      >
        <div
          class="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl text-sm font-bold shadow-2xs"
          :class="{
            'bg-emerald-100 text-emerald-700': toast.type === 'success',
            'bg-blue-100 text-blue-700': toast.type === 'info',
            'bg-rose-100 text-rose-700': toast.type === 'error',
          }"
        >
          <span v-if="toast.type === 'success'">✓</span>
          <span v-else-if="toast.type === 'info'">ℹ</span>
          <span v-else>⚠</span>
        </div>
        <div class="flex-1 min-w-0 pt-0.5">
          <p class="text-xs font-bold tracking-tight text-slate-900">
            {{ toast.title }}
          </p>
          <p class="mt-0.5 text-xs text-slate-600 leading-relaxed">
            {{ toast.message }}
          </p>
        </div>
        <button
          type="button"
          class="text-slate-400 hover:text-slate-700 rounded-lg p-1 transition cursor-pointer"
          aria-label="Dismiss notification"
          @click="dismissToast"
        >
          <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </Transition>

    <!-- Clean Minimal Header -->
    <header class="border-b border-rule bg-surface sticky top-0 z-30 shadow-xs">
      <div class="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <div class="flex items-center gap-3">
          <a href="#" class="flex items-center text-[#261c7a] hover:opacity-90 transition" @click.prevent="closeDocument()">
            <AxmedLogo class="h-8 w-auto" />
          </a>
          <span class="h-4 w-px bg-rule"></span>
          <span class="text-xs font-semibold text-ink-3">Document Intelligence</span>
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
      <div v-if="!selectedDocument">
        <!-- Uploaded Sources Table -->
        <SourceTable
          :documents="documents"
          :busy="busy"
          @select="openDocument"
          @ingest="openIngest"
          @delete="removeDocument"
          @preview="openSourcePreview"
          @export="exportAllData"
        />
      </div>

      <!-- VIEW 2: SOURCE DETAIL PAGE -->
      <div v-else class="space-y-6">
        <!-- Source Detail Header & Schema Strip -->
        <SourceDetailHeader
          :document="selectedDocument"
          :selected-approach="selectedApproach"
          :busy="busy"
          @back="closeDocument"
          @switch-approach="openCandidateForReview"
          @open-review="isReviewModalOpen = true"
          @reextract="reextract(selectedDocument)"
          @preview="openSourcePreview(selectedDocument)"
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
            :document-mapping-confidence="selectedDocument.mapping_confidence?.score"
            :mapping-issues="selectedDocument.mapping_issues ?? []"
            :field-reviews="selectedDocument.quotation.field_reviews"
            :selected-index="selectedLineIndex"
            @select-line="(idx) => { selectedLineIndex = idx; isDrawerOpen = true; }"
          />
        </section>

        <!-- Empty state placeholder when no product lines were extracted -->
        <div
          v-else-if="selectedDocument.status === 'failed'"
          class="rounded-2xl border border-dashed border-rule bg-surface-alt/40 p-10 text-center"
        >
          <p class="text-xs font-semibold text-ink-2">No product lines extracted from this document.</p>
          <p class="mt-1 text-[11px] text-ink-3">
            Preview the source above to inspect it, or upload a clearer version and try again.
          </p>
        </div>

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

    <SourcePreviewModal
      :document="previewDocument"
      :source-url="previewDocument ? sourceDocumentUrl(previewDocument.id) : ''"
      @close="previewDocument = null"
    />
  </div>
</template>
