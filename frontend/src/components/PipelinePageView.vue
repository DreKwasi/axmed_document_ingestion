<script setup lang="ts">
/** Dedicated top-level page presenting the end-to-end extraction pipeline architecture, interactive draggable flowchart, and dual confidence calculations. */

import { ref } from "vue";
import PipelineFlowchart from "./PipelineFlowchart.vue";

const emit = defineEmits<{
  (e: "back"): void;
  (e: "close"): void;
}>();

type Tab = "pipeline" | "scoring" | "routing";
const activeTab = ref<Tab>("pipeline");

function handleBack() {
  emit("back");
  emit("close");
}
</script>

<template>
  <div class="space-y-6">
    <!-- Top Action / Breadcrumbs Bar -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 rounded-2xl border border-rule bg-surface p-5 shadow-xs">
      <div>
        <div class="flex items-center gap-2">
          <button
            type="button"
            class="inline-flex items-center gap-1.5 text-xs font-semibold text-axmed-primary hover:underline cursor-pointer"
            @click="handleBack"
          >
            <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
            Back to Documents
          </button>
          <span class="text-ink-3">&bull;</span>
          <span class="inline-flex items-center justify-center rounded-md bg-[#261c7a]/10 px-2 py-0.5 text-[10px] font-bold text-[#261c7a] uppercase tracking-wider">
            System Architecture
          </span>
        </div>
        <h1 class="mt-1 text-lg sm:text-xl font-bold text-ink">
          How It Works: Pipeline & Confidence Engine
        </h1>
        <p class="mt-0.5 text-xs text-ink-3">
          Application-controlled semantic extraction, deterministic grounding, and dual confidence scoring.
        </p>
      </div>

      <div class="flex items-center gap-2">
        <button
          type="button"
          class="rounded-xl border border-rule bg-white px-4 py-2 text-xs font-semibold text-ink-2 hover:bg-surface-alt hover:text-ink transition cursor-pointer shadow-2xs"
          @click="handleBack"
        >
          Got it, close guide
        </button>
      </div>
    </div>

    <!-- Main Content Container with Tabs -->
    <div class="rounded-3xl border border-rule bg-surface shadow-xs overflow-hidden">
      <!-- Tab Navigation Buttons -->
      <div class="flex border-b border-rule px-6 bg-surface">
        <button
          type="button"
          class="px-4 py-3 text-xs font-semibold border-b-2 transition cursor-pointer flex items-center gap-1.5"
          :class="activeTab === 'pipeline' ? 'border-[#261c7a] text-[#261c7a]' : 'border-transparent text-ink-3 hover:text-ink'"
          @click="activeTab = 'pipeline'"
        >
          <span>Pipeline Architecture Flowchart</span>
          <span class="rounded bg-sky-100 px-1.5 py-0.2 text-[9px] font-bold text-sky-700">Interactive Canvas</span>
        </button>
        <button
          type="button"
          class="px-4 py-3 text-xs font-semibold border-b-2 transition cursor-pointer"
          :class="activeTab === 'scoring' ? 'border-[#261c7a] text-[#261c7a]' : 'border-transparent text-ink-3 hover:text-ink'"
          @click="activeTab = 'scoring'"
        >
          Confidence Calculations & Provenance
        </button>
        <button
          type="button"
          class="px-4 py-3 text-xs font-semibold border-b-2 transition cursor-pointer"
          :class="activeTab === 'routing' ? 'border-[#261c7a] text-[#261c7a]' : 'border-transparent text-ink-3 hover:text-ink'"
          @click="activeTab = 'routing'"
        >
          Decision Gates & Review Routing
        </button>
      </div>

      <!-- Tab Content Area -->
      <div class="p-6 sm:p-8 space-y-6">
        <!-- ================================================================= -->
        <!-- TAB 1: PIPELINE FLOWCHART                                         -->
        <!-- ================================================================= -->
        <div v-if="activeTab === 'pipeline'" class="space-y-6">
          <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div>
              <h2 class="text-sm font-bold text-ink">End-to-End Extraction Pipeline</h2>
              <p class="mt-0.5 text-xs text-ink-2 leading-relaxed">
                The extraction engine operates under an <strong>application-controlled architecture</strong>: deterministic Python code coordinates every preparation step, model invocation, validation gate, and investigation run. Large Language Models are isolated to semantic reasoning; they never fabricate provenance or decide pipeline termination.
              </p>
            </div>
          </div>

          <!-- Draggable & Zoomable Flowchart Component -->
          <PipelineFlowchart height="660px" />

          <!-- Key Architectural Principles -->
          <div>
            <h3 class="text-xs font-bold uppercase tracking-wider text-ink-3 mb-3">Core Architectural Safeguards</h3>
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <div class="rounded-2xl border border-rule bg-surface-alt/40 p-4">
                <div class="flex items-center gap-2 text-axmed-primary">
                  <span class="text-sm">🛡️</span>
                  <h4 class="text-xs font-bold uppercase tracking-wider text-ink">Zero Evidence Hallucination</h4>
                </div>
                <p class="mt-2 text-xs text-ink-2 leading-relaxed">
                  The primary extraction prompt is strictly forbidden from generating source evidence. Evidence records can only be minted through verified grounding claims validated directly against source offsets.
                </p>
              </div>

              <div class="rounded-2xl border border-rule bg-surface-alt/40 p-4">
                <div class="flex items-center gap-2 text-axmed-primary">
                  <span class="text-sm">🔁</span>
                  <h4 class="text-xs font-bold uppercase tracking-wider text-ink">Bounded Investigation</h4>
                </div>
                <p class="mt-2 text-xs text-ink-2 leading-relaxed">
                  Instead of unbounded tool loops, ungrounded fields enter a hard-capped loop (max 3 runs) where all remaining ungrounded fields are investigated together with targeted context.
                </p>
              </div>

              <div class="rounded-2xl border border-rule bg-surface-alt/40 p-4">
                <div class="flex items-center gap-2 text-axmed-primary">
                  <span class="text-sm">📐</span>
                  <h4 class="text-xs font-bold uppercase tracking-wider text-ink">Derived Provenance Reuse</h4>
                </div>
                <p class="mt-2 text-xs text-ink-2 leading-relaxed">
                  When normalizers calculate pack prices from unit quotes (<code class="bg-surface-alt px-1 py-0.5 rounded text-[11px]">price × units</code>), the derived value automatically inherits provenance to avoid false missing-evidence flags.
                </p>
              </div>

              <div class="rounded-2xl border border-rule bg-surface-alt/40 p-4">
                <div class="flex items-center gap-2 text-axmed-primary">
                  <span class="text-sm">👁️</span>
                  <h4 class="text-xs font-bold uppercase tracking-wider text-ink">Continuous Quality & Peers</h4>
                </div>
                <p class="mt-2 text-xs text-ink-2 leading-relaxed">
                  OCR legibility is a continuous quality signal, not a pre-extraction rejection gate. OCR-assisted and direct-vision pipelines run as peers; low-legibility images are marked non-approvable post-extraction.
                </p>
              </div>
            </div>
          </div>
        </div>

        <!-- ================================================================= -->
        <!-- TAB 2: CONFIDENCE CALCULATIONS                                    -->
        <!-- ================================================================= -->
        <div v-else-if="activeTab === 'scoring'" class="space-y-6">
          <div>
            <h2 class="text-sm font-bold text-ink">Dual Confidence Model</h2>
            <p class="mt-1 text-xs text-ink-2 leading-relaxed">
              The platform separates <strong>Extraction Confidence</strong> (physical fidelity of the raw source) from <strong>Mapping Confidence</strong> (provenance certainty that a value belongs to its schema field).
            </p>
          </div>

          <!-- 1. Extraction Confidence Formula -->
          <div class="rounded-2xl border border-rule bg-surface p-5 space-y-3">
            <div class="flex items-center justify-between">
              <h3 class="text-xs font-bold uppercase tracking-wider text-ink flex items-center gap-2">
                <span class="h-2 w-2 rounded-full bg-blue-500"></span>
                1. Extraction Confidence (Document Level)
              </h3>
              <span class="text-[10px] font-mono text-ink-3">Formula: &Sigma;(Weight &times; Factor)</span>
            </div>
            <p class="text-xs text-ink-2 leading-relaxed">
              Measures how legible and machine-readable the uploaded source file was during ingestion:
            </p>
            <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-1">
              <div class="rounded-xl border border-rule bg-surface-alt/60 p-3">
                <div class="flex items-center justify-between">
                  <span class="text-xs font-semibold text-ink">Machine Readability</span>
                  <span class="text-xs font-bold text-axmed-primary">30%</span>
                </div>
                <p class="mt-1 text-[11px] text-ink-3 leading-tight">
                  100% for JSON/native text/email; 40–70% for scanned documents.
                </p>
              </div>
              <div class="rounded-xl border border-rule bg-surface-alt/60 p-3">
                <div class="flex items-center justify-between">
                  <span class="text-xs font-semibold text-ink">Parser Quality</span>
                  <span class="text-xs font-bold text-axmed-primary">25%</span>
                </div>
                <p class="mt-1 text-[11px] text-ink-3 leading-tight">
                  Good (100%), Mixed (70%), or Poor (40%) parser output status.
                </p>
              </div>
              <div class="rounded-xl border border-rule bg-surface-alt/60 p-3">
                <div class="flex items-center justify-between">
                  <span class="text-xs font-semibold text-ink">Text Legibility</span>
                  <span class="text-xs font-bold text-axmed-primary">45%</span>
                </div>
                <p class="mt-1 text-[11px] text-ink-3 leading-tight">
                  100% for non-OCR; for scans, mean OCR score combined with % legible lines.
                </p>
              </div>
            </div>
          </div>

          <!-- 2. The 5-Tier Provenance Hierarchy -->
          <div class="rounded-2xl border border-rule bg-surface p-5 space-y-4">
            <div class="flex items-center justify-between">
              <h3 class="text-xs font-bold uppercase tracking-wider text-ink flex items-center gap-2">
                <span class="h-2 w-2 rounded-full bg-[#261c7a]"></span>
                2. The 5-Tier Deterministic Provenance Hierarchy (Field Level)
              </h3>
              <span class="text-[10px] font-mono text-ink-3">backend/app/extraction/confidence.py</span>
            </div>
            <p class="text-xs text-ink-2 leading-relaxed">
              In <code class="bg-surface-alt px-1 py-0.5 rounded text-[11px]">_classify_mapping()</code>, every extracted field receives a deterministic base score according to the physical nature of its source evidence:
            </p>

            <div class="overflow-x-auto rounded-xl border border-rule">
              <table class="w-full text-left text-xs">
                <thead class="bg-surface-alt text-[10px] font-bold uppercase tracking-wider text-ink-2 border-b border-rule">
                  <tr>
                    <th class="px-4 py-2.5">Tier</th>
                    <th class="px-4 py-2.5">Base Score</th>
                    <th class="px-4 py-2.5">Condition in Code</th>
                    <th class="px-4 py-2.5">Reason String & Interpretation</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-rule font-sans">
                  <tr class="hover:bg-surface-alt/50">
                    <td class="px-4 py-3 font-bold text-ink">Tier 1</td>
                    <td class="px-4 py-3 font-mono font-bold text-emerald-700">100% (High)</td>
                    <td class="px-4 py-3 font-mono text-[11px] text-ink-2">human_corrected, direct_json</td>
                    <td class="px-4 py-3 text-ink-2">
                      <em>"the source explicitly identifies this value as this field"</em>
                      <span class="block text-[11px] text-ink-3">Unambiguous 1:1 machine schema key (e.g. JSON key "price").</span>
                    </td>
                  </tr>
                  <tr class="hover:bg-surface-alt/50">
                    <td class="px-4 py-3 font-bold text-ink">Tier 2</td>
                    <td class="px-4 py-3 font-mono font-bold text-emerald-700">92% (High)</td>
                    <td class="px-4 py-3 font-mono text-[11px] text-ink-2">row, column, or cell</td>
                    <td class="px-4 py-3 text-ink-2">
                      <em>"the value is linked to a specific source row or cell..."</em>
                      <span class="block text-[11px] text-ink-3">Pinned to structured grid coordinates in PDF or OCR tables.</span>
                    </td>
                  </tr>
                  <tr class="hover:bg-surface-alt/50 bg-amber-50/40">
                    <td class="px-4 py-3 font-bold text-amber-900">Tier 3</td>
                    <td class="px-4 py-3 font-mono font-bold text-amber-800">82% (Medium)</td>
                    <td class="px-4 py-3 font-mono text-[11px] text-ink-2">source_path or source_location</td>
                    <td class="px-4 py-3 text-ink-2">
                      <em>"the value was found in the source, but the source did not explicitly identify it as this field"</em>
                      <span class="block text-[11px] text-ink-3">Found in unstructured text (e.g. Email body). Grounded, but lacks machine keys.</span>
                    </td>
                  </tr>
                  <tr class="hover:bg-surface-alt/50">
                    <td class="px-4 py-3 font-bold text-ink">Tier 4</td>
                    <td class="px-4 py-3 font-mono font-bold text-amber-700">70% (Medium)</td>
                    <td class="px-4 py-3 font-mono text-[11px] text-ink-2">evidence present, no location</td>
                    <td class="px-4 py-3 text-ink-2">
                      <em>"the value was extracted, but its exact source location was not recorded"</em>
                    </td>
                  </tr>
                  <tr class="hover:bg-surface-alt/50 bg-rose-50/40">
                    <td class="px-4 py-3 font-bold text-rose-900">Tier 5</td>
                    <td class="px-4 py-3 font-mono font-bold text-rose-700">30% (Low)</td>
                    <td class="px-4 py-3 font-mono text-[11px] text-ink-2">category mismatch or conflict</td>
                    <td class="px-4 py-3 text-ink-2">
                      <em>"the source-to-schema association conflicts with another value or validation"</em>
                      <span class="block text-[11px] text-ink-3">Contradiction (e.g., source quantity mapped to price field).</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <!-- Mathematical Bonus -->
            <div class="rounded-xl border border-emerald-200 bg-emerald-50/60 p-3.5 flex items-start gap-3">
              <span class="text-emerald-700 text-sm">💡</span>
              <div class="text-xs text-emerald-950 leading-relaxed">
                <strong>Commercial Math Bonus (+5%):</strong> When mathematical validation passes across related fields (e.g. <code class="bg-white/80 px-1 py-0.5 rounded text-emerald-900">quoted_price × quantity = extended_price</code> or <code class="bg-white/80 px-1 py-0.5 rounded text-emerald-900">unit_price × units_per_pack = pack_price</code>), affected fields receive a +5% confidence boost (capped at 100%) with the note <em>"; related values agree"</em>.
              </div>
            </div>

            <!-- Aggregation Formula -->
            <div class="rounded-xl border border-rule bg-surface-alt/40 p-3.5 flex items-center justify-between">
              <div>
                <h4 class="text-xs font-bold text-ink">Product Line Mapping Confidence Formula</h4>
                <p class="text-[11px] text-ink-3">A line item's mapping score is the arithmetic mean of all its populated field scores:</p>
              </div>
              <div class="font-mono text-xs font-bold text-[#261c7a] bg-white border border-rule px-3 py-1.5 rounded-lg shadow-2xs">
                Line Score = round( &Sigma; FieldScores / TotalFields )
              </div>
            </div>
          </div>

          <!-- 3. Why 82% has 0 issues -->
          <div class="rounded-2xl border border-rule bg-surface p-5 space-y-3">
            <h3 class="text-xs font-bold uppercase tracking-wider text-ink flex items-center gap-2">
              <span class="h-2 w-2 rounded-full bg-amber-500"></span>
              Why a Line Item Can Show 82% Confidence with 0 Mapping Issues
            </h3>
            <p class="text-xs text-ink-2 leading-relaxed">
              Reviewers often wonder why an extraction has <strong>82% Mapping Confidence</strong> even when there are <strong>0 mapping issues</strong>:
            </p>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-1">
              <div class="rounded-xl border border-rule bg-surface-alt/40 p-3.5 space-y-1">
                <span class="text-xs font-bold text-ink">What 82% Means (Provenance Band)</span>
                <p class="text-xs text-ink-3 leading-relaxed">
                  82% indicates that all data was extracted from <strong>unstructured text (like an email body)</strong>. The system grounded every field against source quotes, but natural prose lacks explicit machine keys (unlike a JSON API which scores 100%).
                </p>
              </div>
              <div class="rounded-xl border border-rule bg-surface-alt/40 p-3.5 space-y-1">
                <span class="text-xs font-bold text-ink">What "0 Issues" Means (Defect Free)</span>
                <p class="text-xs text-ink-3 leading-relaxed">
                  Issues represent <em>actionable defects</em>: completely missing evidence (0%) or contradictory category assignments (30%). If all fields have verified source excerpts and zero mathematical conflicts, there are <strong>0 issues to resolve</strong>.
                </p>
              </div>
            </div>
          </div>
        </div>

        <!-- ================================================================= -->
        <!-- TAB 3: DECISION GATES & ROUTING                                   -->
        <!-- ================================================================= -->
        <div v-else-if="activeTab === 'routing'" class="space-y-6">
          <div>
            <h2 class="text-sm font-bold text-ink">Automated Quality Gates & Review Routing</h2>
            <p class="mt-1 text-xs text-ink-2 leading-relaxed">
              Based on the extraction and mapping confidence scores, the platform routes each incoming supplier quotation into one of three operational states:
            </p>
          </div>

          <div class="space-y-4">
            <!-- Pre-approved -->
            <div class="rounded-2xl border border-emerald-200 bg-emerald-50/40 p-5">
              <div class="flex items-center justify-between">
                <span class="inline-flex items-center gap-1.5 rounded-full bg-emerald-100 px-3 py-1 text-xs font-bold text-emerald-800">
                  <span class="h-2 w-2 rounded-full bg-emerald-600"></span>
                  Pre-approved
                </span>
                <span class="text-xs font-mono font-semibold text-emerald-900">Zero Human Intervention Needed</span>
              </div>
              <ul class="mt-3 list-disc list-inside space-y-1 text-xs text-emerald-950">
                <li><strong>100% Extraction Confidence:</strong> Natively structured file (JSON or clean native PDF).</li>
                <li><strong>100% Mapping Confidence:</strong> All fields mapped to unambiguous 1:1 schema keys.</li>
                <li><strong>0 Mapping Issues:</strong> Zero ungrounded fields, math conflicts, or missing evidence.</li>
              </ul>
            </div>

            <!-- Needs review -->
            <div class="rounded-2xl border border-amber-200 bg-amber-50/40 p-5">
              <div class="flex items-center justify-between">
                <span class="inline-flex items-center gap-1.5 rounded-full bg-amber-100 px-3 py-1 text-xs font-bold text-amber-800">
                  <span class="h-2 w-2 rounded-full bg-amber-600"></span>
                  Needs review
                </span>
                <span class="text-xs font-mono font-semibold text-amber-900">Routed to Review Desk</span>
              </div>
              <ul class="mt-3 list-disc list-inside space-y-1 text-xs text-amber-950">
                <li>Unstructured email or PDF table where mapping confidence is in the 82%–92% range.</li>
                <li>Any actionable mapping issues (e.g. ungrounded supplier terms, category ambiguity).</li>
                <li>Enables human reviewer to inspect source excerpts, edit values, or confirm quotation.</li>
              </ul>
            </div>

            <!-- Material unusable -->
            <div class="rounded-2xl border border-rose-200 bg-rose-50/40 p-5">
              <div class="flex items-center justify-between">
                <span class="inline-flex items-center gap-1.5 rounded-full bg-rose-100 px-3 py-1 text-xs font-bold text-rose-800">
                  <span class="h-2 w-2 rounded-full bg-rose-600"></span>
                  Material unusable (Auto-rejected)
                </span>
                <span class="text-xs font-mono font-semibold text-rose-900">Non-Approvable Policy Lock</span>
              </div>
              <ul class="mt-3 list-disc list-inside space-y-1.5 text-xs text-rose-950">
                <li><strong>Continuous Quality Signal (No Pre-Gate):</strong> OCR legibility is a continuous quality score, not a pre-extraction rejection gate. Both OCR-assisted and direct-vision extraction run as peers even on degraded or glare-affected scans.</li>
                <li><strong>Deterministic 50% Threshold:</strong> When source extraction confidence drops below <strong>50%</strong> for an image, the post-extraction policy marks the document as <code class="font-mono text-[11px] bg-rose-100 px-1 py-0.5 rounded text-rose-900">auto_rejected</code>.</li>
                <li><strong>Approval Strictly Blocked:</strong> Neither peer attempt can become canonical or be approved, preventing unverified or hallucinated values from entering procurement.</li>
                <li><strong>Retained Inline for Audit:</strong> Original source media, extracted candidates, and provenance evidence are preserved inline for human review and inspection.</li>
              </ul>
            </div>
          </div>
        </div>
      </div>

      <!-- Page Footer -->
      <div class="border-t border-rule px-6 py-4 bg-surface-alt/40 flex items-center justify-between">
        <span class="text-xs text-ink-3">
          Deterministic Engine: <code class="font-mono text-[11px] text-ink-2">Python 3.13 + Gemini 3.5 Flash Lite</code>
        </span>
        <button
          type="button"
          class="rounded-xl bg-[#261c7a] px-4 py-2 text-xs font-semibold text-white transition hover:bg-[#1e155c] cursor-pointer shadow-xs"
          @click="handleBack"
        >
          Got it, close guide
        </button>
      </div>
    </div>
  </div>
</template>
