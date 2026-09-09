<script setup lang="ts">
/** Source detail header presenting document metadata, peer switcher, and review actions. */

import { computed } from "vue";
import type { DocumentResponse } from "@/types";

// --- Section 1: Props & Emits ---

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
  (event: "preview"): void;
  (event: "openHowItWorks"): void;
}>();

// --- Section 2: Presentation & Status Derivations ---

/**
 * Whether the document has been approved by human review or policy.
 */
function isApproved(doc: DocumentResponse): boolean {
  return doc.status === "approved" || doc.quotation?.review_status === "approved";
}

/**
 * Whether the document has been rejected by human review or policy.
 */
function isRejected(doc: DocumentResponse): boolean {
  return doc.status === "rejected" || doc.status === "auto_rejected" || doc.quotation?.review_status === "rejected";
}

/**
 * Derives categorical status key ('ready' | 'review' | 'needs_attention' | 'processing').
 *
 * @param doc Target document response.
 * @returns Categorical status key.
 */
function statusKey(doc: DocumentResponse): "approved" | "preapproved" | "review" | "rejected" | "failed" | "processing" {
  if (isApproved(doc)) return "approved";
  if (doc.status === "failed") return "failed";
  if (doc.status === "pre_approved" || doc.quotation?.review_status === "pre_approved") return "preapproved";
  if (isRejected(doc)) return "rejected";
  if (doc.status === "pending_review") return "review";
  return "processing";
}

/** Human-readable status label */
const statusLabel = computed(() => {
  if (props.document.status === "failed") return "Extraction failed";
  if (props.document.status === "auto_rejected") return "Material unusable";
  if (isRejected(props.document)) return "Rejected";
  if (isApproved(props.document)) return "Approved";
  const map = {
    approved: "Approved",
    preapproved: "Pre-approved",
    review: "Needs review",
    rejected: "Rejected",
    failed: "Extraction failed",
    processing: "Processing",
  };
  return map[statusKey(props.document)];
});

/** Formatted title combining supplier, quotation reference, and active reading approach */
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

/** Descriptive extraction confidence label */
const confidence = computed(() => {
  const summary = props.document.extraction_confidence;
  if (!summary) return "Extraction confidence unavailable";
  return `Extraction confidence ${summary.score}% (${summary.band})`;
});

/** Non-empty Harmonized System (HS) tariff codes from commercial terms */
const hsCodes = computed(() => props.document.quotation?.commercial_terms?.hs_codes?.filter(Boolean) ?? []);

/** Human-readable shipping transit duration */
const transitDuration = computed(() => {
  const terms = props.document.quotation?.commercial_terms;
  if (!terms) return null;
  if (terms.transit_time_min_days != null && terms.transit_time_max_days != null) {
    return terms.transit_time_min_days === terms.transit_time_max_days
      ? `${terms.transit_time_min_days} days`
      : `${terms.transit_time_min_days}–${terms.transit_time_max_days} days`;
  }
  if (terms.transit_time_days != null) {
    return `${terms.transit_time_days} days`;
  }
  if (terms.transit_time_min_days != null) {
    return `≥ ${terms.transit_time_min_days} days`;
  }
  if (terms.transit_time_max_days != null) {
    return `≤ ${terms.transit_time_max_days} days`;
  }
  return null;
});

/** Uppercase format badge (PDF, JSON, EML, IMAGE) */
const formatBadge = computed(() => {
  const lower = props.document.filename.toLowerCase();
  if (lower.endsWith(".pdf")) return "PDF";
  if (lower.endsWith(".json")) return "JSON";
  if (lower.endsWith(".eml")) return "EML";
  if (lower.endsWith(".png") || lower.endsWith(".jpg") || lower.endsWith(".jpeg")) return "IMAGE";
  return props.document.source_system?.toUpperCase() || "FILE";
});

/** Formatted external system name (e.g. "sap v2.1") if applicable */
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

/** Whether the document is in an actionable pending_review state */
const canReview = computed(() => {
  return (
    props.document.status === "pending_review" &&
    props.document.quotation?.review_status === "pending_review"
  );
});

/** CSS text color class based on status key */
const statusTextClass = computed(() => {
  const map = {
    approved: "text-emerald-800",
    preapproved: "text-sky-800",
    review: "text-amber-900",
    rejected: "text-rose-800",
    failed: "text-rose-800",
    processing: "text-ink-3",
  };
  return map[statusKey(props.document)];
});

/** CSS indicator dot class based on status key */
const statusDotClass = computed(() => {
  const map = {
    approved: "bg-emerald-600",
    preapproved: "bg-sky-600",
    review: "bg-amber-500",
    rejected: "bg-rose-600",
    failed: "bg-rose-600",
    processing: "bg-ink-3 animate-pulse",
  };
  return map[statusKey(props.document)];
});
</script>

<template>
  <div class="space-y-4">
    <!-- Back link -->
    <div>
      <a
        href="#"
        role="button"
        class="inline-flex items-center gap-1.5 text-xs font-semibold text-ink-3 hover:text-axmed-primary transition cursor-pointer"
        @click.prevent="emit('back')"
      >
        <span>←</span> Back to sources
      </a>
    </div>

    <!-- Main Header Card -->
    <div class="rounded-2xl border border-rule bg-surface p-6 shadow-xs">
      <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div class="space-y-2">
          <!-- Document Title -->
          <h1 class="text-2xl font-extrabold tracking-tight text-ink sm:text-3xl">
            {{ sourceTitle }}
          </h1>

          <!-- Peer Reading Switcher (for image documents) -->
          <div
            v-if="document.image_extraction_attempts && document.image_extraction_attempts.length > 1"
            class="mt-2 inline-flex items-center gap-1 rounded-xl border border-rule bg-surface-alt p-1 text-xs"
          >
            <span class="px-2 font-medium text-ink-3 text-[11px]">Reading:</span>
            <button
              v-for="attempt in document.image_extraction_attempts"
              :key="attempt.approach"
              type="button"
              class="rounded-lg px-2.5 py-1 font-semibold transition cursor-pointer inline-flex items-center gap-1.5"
              :class="
                (selectedApproach || document.image_extraction_attempts[0]?.approach) === attempt.approach
                  ? 'bg-surface text-axmed-primary shadow-2xs font-bold border border-rule'
                  : 'text-ink-2 hover:text-ink'
              "
              :disabled="busy"
              @click="emit('switchApproach', attempt.approach)"
            >
              <span>{{ attempt.approach === "ocr_assisted" ? "OCR-assisted" : "Direct vision" }}</span>
              <span
                v-if="attempt.status === 'failed'"
                class="rounded px-1 py-0.2 text-[10px] font-medium bg-amber-100/80 text-amber-800"
              >
                Unclear
              </span>
            </button>
          </div>

          <!-- Informational Metadata Line (Clean text & status dot, NOT buttons) -->
          <div class="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-ink-2">
            <!-- Format Tag -->
            <span class="rounded-md bg-surface-alt px-2 py-0.5 text-[10px] font-mono font-bold uppercase tracking-wider text-ink-2 border border-rule">
              {{ formatBadge }}
            </span>

            <template v-if="externalSystem">
              <span class="text-rule-dark">·</span>
              <span class="font-medium text-ink-2 text-[11px]">{{ externalSystem }}</span>
            </template>

            <template v-if="document.parsed_summary?.page_count">
              <span class="text-rule-dark">·</span>
              <span class="text-ink-3 text-[11px]">
                {{ document.parsed_summary.page_count }} {{ document.parsed_summary.page_count === 1 ? 'page' : 'pages' }}
              </span>
            </template>

            <span class="text-rule-dark">·</span>

            <!-- Extraction confidence describes source recovery only. -->
            <span class="font-medium text-ink-2">
              {{ confidence }}
            </span>

            <span class="text-rule-dark">·</span>

            <!-- Status Indicator with dot -->
            <span class="inline-flex items-center gap-1.5 font-semibold" :class="statusTextClass">
              <span class="h-2 w-2 rounded-full" :class="statusDotClass"></span>
              {{ statusLabel }}
            </span>
          </div>
        </div>

        <!-- Distinct Action Buttons -->
        <div class="flex flex-wrap items-center gap-2 sm:gap-3 shrink-0 w-full sm:w-auto">
          <!-- Secondary Action: Open Original -->
          <button
            type="button"
            class="inline-flex flex-1 sm:flex-none justify-center items-center gap-1.5 rounded-xl border border-rule bg-surface px-3.5 py-2 text-xs font-semibold text-ink-2 hover:bg-surface-alt hover:text-ink hover:border-rule-dark transition shadow-2xs cursor-pointer"
            @click="emit('preview')"
          >
            <span>Preview source</span>
            <svg class="h-3.5 w-3.5 text-ink-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z" /><circle cx="12" cy="12" r="2.5" />
            </svg>
          </button>

          <!-- Re-extract Action for JSON sources when extraction failed -->
          <button
            v-if="document.status === 'failed' && document.filename.toLowerCase().endsWith('.json')"
            type="button"
            class="inline-flex flex-1 sm:flex-none justify-center items-center gap-1.5 rounded-xl bg-[#261c7a] px-4 py-2 text-xs font-bold text-white shadow-xs hover:bg-[#1e155c] active:bg-[#150f42] transition focus:outline-none focus:ring-2 focus:ring-[#261c7a] focus:ring-offset-1 disabled:opacity-50 cursor-pointer"
            :disabled="busy"
            @click="emit('reextract')"
          >
            <span>Extract again</span>
          </button>

          <!-- Reviewed State Confirmation Pill -->
          <span
            v-else-if="isApproved(document)"
            class="inline-flex flex-1 sm:flex-none justify-center items-center gap-1.5 rounded-xl bg-ok-bg border border-ok/30 px-3.5 py-2 text-xs font-bold text-ok shadow-2xs"
          >
            <span class="text-xs">✓</span>
            <span>Approved</span>
          </span>
          <span
            v-else-if="isRejected(document)"
            class="inline-flex flex-1 sm:flex-none justify-center items-center gap-1.5 rounded-xl bg-down-bg border border-down/30 px-3.5 py-2 text-xs font-bold text-down shadow-2xs"
          >
            <span class="text-xs">✕</span>
            <span>{{ document.status === "auto_rejected" ? "Material unusable" : "Rejected" }}</span>
          </span>

          <!-- Primary CTA Action: Review Source -->
          <button
            v-else-if="canReview"
            type="button"
            class="inline-flex flex-1 sm:flex-none justify-center items-center gap-1.5 rounded-xl bg-[#261c7a] px-4 py-2 text-xs font-bold text-white shadow-xs hover:bg-[#1e155c] active:bg-[#150f42] transition focus:outline-none focus:ring-2 focus:ring-[#261c7a] focus:ring-offset-1 disabled:opacity-50 cursor-pointer"
            :disabled="busy"
            @click="emit('openReview')"
          >
            <span class="text-cyan-300">✓</span>
            <span>Review source</span>
          </button>

          <!-- How it works guide trigger -->
          <button
            type="button"
            class="inline-flex flex-1 sm:flex-none justify-center items-center gap-1.5 rounded-xl border border-rule bg-surface px-3.5 py-2 text-xs font-semibold text-ink-2 hover:bg-surface-alt hover:text-ink hover:border-rule-dark transition shadow-2xs cursor-pointer"
            @click="emit('openHowItWorks')"
          >
            <span>How it works</span>
            <svg class="h-3.5 w-3.5 text-axmed-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </button>
        </div>
      </div>

      <!-- Metadata Strip (only shown when quotation data is available) -->
      <div v-if="document.quotation" class="mt-5 border-t border-rule pt-4">
        <div class="grid grid-cols-2 gap-3 md:grid-cols-4 text-xs">
          <div class="rounded-xl bg-surface-alt p-3 border border-rule">
            <p class="text-[10px] font-bold uppercase tracking-wider text-ink-3">Supplier</p>
            <p class="mt-1 font-semibold text-ink truncate" :title="document.quotation?.supplier.name ?? '—'">
              {{ document.quotation?.supplier.name || "—" }}
              <span v-if="document.quotation?.supplier.country" class="text-ink-3 text-[11px]">
                ({{ document.quotation.supplier.country }})
              </span>
            </p>
          </div>

          <div class="rounded-xl bg-surface-alt p-3 border border-rule">
            <p class="text-[10px] font-bold uppercase tracking-wider text-ink-3">Delivery Terms</p>
            <p class="mt-1 font-semibold text-ink">
              {{ document.quotation?.commercial_terms?.currency || "—" }}
              <span v-if="document.quotation?.commercial_terms?.incoterm" class="text-axmed-primary font-bold">
                · {{ document.quotation.commercial_terms.incoterm }}
              </span>
              <span v-if="document.quotation?.commercial_terms?.incoterm_named_place" class="text-ink-3 text-[11px]">
                ({{ document.quotation.commercial_terms.incoterm_named_place }})
              </span>
            </p>
            <p v-if="document.quotation?.commercial_terms?.incoterm_country" class="mt-1 text-[11px] text-ink-3">
              Delivery country: {{ document.quotation.commercial_terms.incoterm_country }}
            </p>
            <p v-if="transitDuration" class="mt-1 text-[11px] text-ink-3">
              Transit: {{ transitDuration }}
            </p>
            <p v-if="document.quotation?.commercial_terms?.payment_terms" class="mt-1 text-[11px] text-ink-3">
              Payment: {{ document.quotation.commercial_terms.payment_terms }}
            </p>
            <p v-if="hsCodes.length" class="mt-1 text-[11px] text-ink-3">
              HS codes: {{ hsCodes.join(" · ") }}
            </p>
          </div>

          <div class="rounded-xl bg-surface-alt p-3 border border-rule">
            <p class="text-[10px] font-bold uppercase tracking-wider text-ink-3">Document Type / Ref</p>
            <p class="mt-1 font-semibold text-ink truncate" :title="document.quotation?.quotation_reference ?? '—'">
              {{ document.quotation?.quotation_reference || "—" }}
              <span v-if="document.quotation?.document_type" class="text-ink-3 text-[11px]">
                · {{ document.quotation.document_type }}
              </span>
            </p>
          </div>

          <div class="rounded-xl bg-surface-alt p-3 border border-rule">
            <p class="text-[10px] font-bold uppercase tracking-wider text-ink-3">Against RFQ</p>
            <p class="mt-1 font-semibold text-ink truncate" :title="document.quotation?.rfq_reference ?? '—'">
              {{ document.quotation?.rfq_reference || "—" }}
            </p>
          </div>
        </div>
      </div>

      <!-- Extraction State Summary (when extraction failed) -->
      <div v-else-if="['failed', 'auto_rejected'].includes(document.status) && document.failure_reason" class="mt-5 border-t border-rule pt-4">
        <div class="rounded-xl bg-surface-alt p-4 border border-rule text-xs">
          <p class="text-[10px] font-bold uppercase tracking-wider text-ink-3">Extraction state</p>
          <p class="mt-1 font-semibold text-ink">
            {{ document.status === "auto_rejected" ? "Material warning" : "Extraction failed" }}
            <span class="font-normal text-ink-2"> — {{ document.failure_reason }}</span>
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
