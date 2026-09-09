<script setup lang="ts">
/** Review modal dialog for capturing human audit decisions on extracted quotations. */

import { computed, ref, watch } from "vue";
import type { DocumentResponse } from "@/types";

// --- Section 1: Props & Emits ---

const props = defineProps<{
  isOpen: boolean;
  document: DocumentResponse;
  busy: boolean;
}>();

const emit = defineEmits<{
  (event: "close"): void;
  (event: "approve", note?: string): void;
  (event: "reject", payload: { reason: string; note?: string }): void;
}>();

// --- Section 2: State & Reset Watcher ---

const note = ref("");
const rejectionReason = ref("incorrect_extraction");

watch(
  () => props.isOpen,
  (open) => {
    if (open) {
      note.value = "";
      rejectionReason.value = "incorrect_extraction";
    }
  }
);

// --- Section 3: Computed Derivations ---

/** Whether document has blocking error-level validation issues preventing approval */
const hasBlockingIssue = computed(() => {
  return props.document.quotation?.review_issues.some((issue) => issue.severity === "error") ?? false;
});

/** Action button label reflecting whether document had prior human corrections */
const approvalLabel = computed(() => {
  return props.document.quotation?.has_corrections ? "Approve corrected source" : "Approve source";
});

/** Formatted source title combining supplier, quotation reference, or filename */
const sourceTitle = computed(() => {
  if (props.document.source_name) return props.document.source_name;
  const supplier = props.document.quotation?.supplier.name;
  const ref = props.document.quotation?.quotation_reference;
  if (supplier && ref) return `${supplier} · ${ref}`;
  if (supplier) return `${supplier} quotation`;
  return props.document.filename;
});

// --- Section 4: Action Handlers ---

function onApprove() {
  emit("approve", note.value.trim() || undefined);
}

function onReject() {
  emit("reject", { reason: rejectionReason.value, note: note.value.trim() || undefined });
}
</script>

<template>
  <div
    v-if="isOpen"
    class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-3 sm:p-4 backdrop-blur-xs transition-opacity"
    role="dialog"
    aria-modal="true"
    aria-labelledby="review-modal-title"
  >
    <div
      class="w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-2xl border border-rule bg-surface p-4 sm:p-6 shadow-2xl transition-all"
    >
      <div class="flex items-start justify-between border-b border-rule pb-3 sm:pb-4">
        <div>
          <h2 id="review-modal-title" class="text-lg sm:text-xl font-bold text-ink">Review Source Decision</h2>
          <p class="mt-1 text-xs text-ink-3">Every completed extraction requires a human decision.</p>
        </div>
        <button
          type="button"
          class="rounded-lg p-1.5 text-ink-3 hover:bg-surface-alt hover:text-ink transition cursor-pointer"
          aria-label="Close dialog"
          @click="emit('close')"
        >
          ✕
        </button>
      </div>

      <div class="mt-4 rounded-xl bg-surface-alt p-3.5 text-xs text-ink-2 space-y-1 border border-rule">
        <p><span class="font-semibold text-ink">Source:</span> {{ sourceTitle }}</p>
        <p><span class="font-semibold text-ink">File:</span> {{ document.filename }}</p>
        <p v-if="document.quotation">
          <span class="font-semibold text-ink">Products:</span> {{ document.quotation.line_items.length }} extracted
        </p>
      </div>

      <div class="mt-4">
        <label for="review-note" class="block text-xs font-semibold text-ink mb-1.5">
          Review Note <span class="text-ink-3 font-normal">(optional)</span>
        </label>
        <textarea
          id="review-note"
          v-model="note"
          rows="3"
          class="w-full rounded-xl border border-rule-dark p-3 text-sm text-ink focus:border-axmed-primary focus:ring-1 focus:ring-axmed-primary focus:outline-none transition placeholder:text-ink-3 bg-surface"
          :aria-label="`Review note for ${document.filename}`"
          placeholder="Add a reason or context for this approval or rejection..."
        ></textarea>
      </div>

      <div class="mt-4">
        <label for="rejection-reason" class="block text-xs font-semibold text-ink mb-1.5">
          Rejection reason <span class="text-down">(required to reject)</span>
        </label>
        <select
          id="rejection-reason"
          v-model="rejectionReason"
          class="app-select w-full text-sm"
        >
          <option value="incorrect_extraction">Incorrect extraction</option>
          <option value="unreadable_source">Unreadable source</option>
          <option value="unsupported_document">Unsupported document</option>
          <option value="duplicate">Duplicate</option>
          <option value="not_a_quotation">Not a quotation</option>
          <option value="other">Other</option>
        </select>
      </div>

      <div v-if="hasBlockingIssue" class="mt-3 rounded-lg bg-down-bg border border-down/30 p-3 text-xs text-down">
        <span class="font-bold">Cannot approve:</span> Resolve error-level validation issues before approval.
      </div>

      <div class="mt-6 flex items-center justify-end gap-3 border-t border-rule pt-4">
        <button
          type="button"
          class="rounded-xl border border-rule-dark px-4 py-2.5 text-sm font-medium text-ink hover:bg-surface-alt transition focus:outline-none cursor-pointer"
          :disabled="busy"
          @click="emit('close')"
        >
          Cancel
        </button>
        <button
          type="button"
          class="rounded-xl border border-[#fecdca] bg-down-bg px-4 py-2.5 text-sm font-semibold text-down hover:bg-[#fee4e2] transition focus:outline-none disabled:opacity-50 cursor-pointer"
          :disabled="busy"
          @click="onReject"
        >
          Reject
        </button>
        <button
          type="button"
          class="rounded-xl bg-[#261c7a] px-5 py-2.5 text-sm font-semibold text-white shadow-xs hover:bg-[#1e155c] active:bg-[#150f42] transition focus:outline-none disabled:opacity-50 cursor-pointer"
          :disabled="busy || hasBlockingIssue"
          @click="onApprove"
        >
          {{ busy ? "Saving…" : approvalLabel }}
        </button>
      </div>
    </div>
  </div>
</template>
