<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { DocumentResponse } from "@/types";

const props = defineProps<{
  isOpen: boolean;
  document: DocumentResponse;
  busy: boolean;
}>();

const emit = defineEmits<{
  (event: "close"): void;
  (event: "approve", note?: string): void;
  (event: "reject", note?: string): void;
}>();

const note = ref("");

watch(
  () => props.isOpen,
  (open) => {
    if (open) {
      note.value = "";
    }
  }
);

const hasBlockingIssue = computed(() => {
  return props.document.quotation?.review_issues.some((issue) => issue.severity === "error") ?? false;
});

const sourceTitle = computed(() => {
  if (props.document.source_name) return props.document.source_name;
  const supplier = props.document.quotation?.supplier.name;
  const ref = props.document.quotation?.quotation_reference;
  if (supplier && ref) return `${supplier} · ${ref}`;
  if (supplier) return `${supplier} quotation`;
  return props.document.filename;
});

function onApprove() {
  emit("approve", note.value.trim() || undefined);
}

function onReject() {
  emit("reject", note.value.trim() || undefined);
}
</script>

<template>
  <div
    v-if="isOpen"
    class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4 backdrop-blur-xs transition-opacity"
    role="dialog"
    aria-modal="true"
    aria-labelledby="review-modal-title"
  >
    <div
      class="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl transition-all"
    >
      <div class="flex items-start justify-between border-b border-slate-100 pb-4">
        <div>
          <h2 id="review-modal-title" class="text-xl font-bold text-slate-900">Review Source Decision</h2>
          <p class="mt-1 text-xs text-slate-500">Record an overall approval or rejection for this source.</p>
        </div>
        <button
          type="button"
          class="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition"
          aria-label="Close dialog"
          @click="emit('close')"
        >
          ✕
        </button>
      </div>

      <div class="mt-4 rounded-xl bg-slate-50 p-3.5 text-xs text-slate-600 space-y-1 border border-slate-100">
        <p><span class="font-semibold text-slate-700">Source:</span> {{ sourceTitle }}</p>
        <p><span class="font-semibold text-slate-700">File:</span> {{ document.filename }}</p>
        <p v-if="document.quotation">
          <span class="font-semibold text-slate-700">Products:</span> {{ document.quotation.line_items.length }} extracted
          <span v-if="document.extraction_confidence" class="ml-2 font-semibold text-slate-700">
            · Overall Confidence: {{ document.extraction_confidence }}
          </span>
        </p>
      </div>

      <div class="mt-4">
        <label for="review-note" class="block text-xs font-semibold text-slate-700 mb-1.5">
          Review Note <span class="text-slate-400 font-normal">(optional)</span>
        </label>
        <textarea
          id="review-note"
          v-model="note"
          rows="3"
          class="w-full rounded-xl border border-slate-300 p-3 text-sm text-slate-800 focus:border-emerald-600 focus:ring-1 focus:ring-emerald-600 focus:outline-none transition placeholder:text-slate-400"
          :aria-label="`Review note for ${document.filename}`"
          placeholder="Add a reason or context for this approval or rejection..."
        ></textarea>
      </div>

      <div v-if="hasBlockingIssue" class="mt-3 rounded-lg bg-rose-50 border border-rose-200 p-3 text-xs text-rose-700">
        <span class="font-bold">Cannot approve:</span> Resolve error-level validation issues before approval.
      </div>

      <div class="mt-6 flex items-center justify-end gap-3 border-t border-slate-100 pt-4">
        <button
          type="button"
          class="rounded-xl border border-slate-300 px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 transition focus:outline-none"
          :disabled="busy"
          @click="emit('close')"
        >
          Cancel
        </button>
        <button
          type="button"
          class="rounded-xl border border-rose-200 bg-rose-50 px-4 py-2.5 text-sm font-semibold text-rose-700 hover:bg-rose-100 transition focus:outline-none disabled:opacity-50"
          :disabled="busy"
          @click="onReject"
        >
          Reject
        </button>
        <button
          type="button"
          class="rounded-xl bg-emerald-700 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-emerald-800 transition focus:outline-none disabled:opacity-50"
          :disabled="busy || hasBlockingIssue"
          @click="onApprove"
        >
          {{ busy ? "Saving…" : "Approve source" }}
        </button>
      </div>
    </div>
  </div>
</template>
