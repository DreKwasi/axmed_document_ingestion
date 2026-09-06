<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import { confirmMapping, fetchEvaluations, runEvaluation, uploadDocument } from "@/api";
import type { DocumentResponse, EvaluationsResponse } from "@/types";

type Tab = "review" | "evaluations";

const activeTab = ref<Tab>("review");
const selectedDocument = ref<DocumentResponse | null>(null);
const evaluations = ref<EvaluationsResponse | null>(null);
const busy = ref(false);
const errorMessage = ref("");
const fileInput = ref<HTMLInputElement | null>(null);

const statusLabel = computed(() => {
  const status = selectedDocument.value?.status;
  if (status === "needs_mapping_confirmation") return "Mapping needs your confirmation";
  if (status === "needs_mapping_resolution") return "Changed source structure needs review";
  if (status === "needs_review") return "Ready for quotation review";
  if (status === "failed") return "Extraction stopped safely";
  return "Awaiting a document";
});

async function loadEvaluations() {
  evaluations.value = await fetchEvaluations();
}

async function chooseFile(event: Event) {
  const input = event.target as HTMLInputElement;
  const [file] = input.files ?? [];
  if (file) await upload(file);
  input.value = "";
}

async function upload(file: File) {
  busy.value = true;
  errorMessage.value = "";
  try {
    selectedDocument.value = await uploadDocument(file);
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "Upload failed.";
  } finally {
    busy.value = false;
  }
}

async function confirm() {
  if (!selectedDocument.value) return;
  busy.value = true;
  errorMessage.value = "";
  try {
    selectedDocument.value = await confirmMapping(selectedDocument.value.id);
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "Mapping confirmation failed.";
  } finally {
    busy.value = false;
  }
}

async function evaluate() {
  busy.value = true;
  errorMessage.value = "";
  try {
    await runEvaluation();
    await loadEvaluations();
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "Evaluation failed.";
  } finally {
    busy.value = false;
  }
}

onMounted(async () => {
  try {
    await loadEvaluations();
  } catch {
    // The review workflow remains useful when the API is still starting.
  }
});
</script>

<template>
  <main class="app-shell">
    <header class="masthead">
      <a class="wordmark" href="#" aria-label="Axmed source ledger home">
        <span class="wordmark-mark">A</span>
        <span>AXMED</span>
      </a>
      <nav aria-label="Workspace sections">
        <button :class="{ active: activeTab === 'review' }" @click="activeTab = 'review'">Review desk</button>
        <button :class="{ active: activeTab === 'evaluations' }" @click="activeTab = 'evaluations'">Evaluation lab</button>
      </nav>
      <div class="environment-pill"><span></span> Local evidence ledger</div>
    </header>

    <section v-if="activeTab === 'review'" class="review-layout">
      <div class="intro-panel">
        <p class="eyebrow">Supplier intelligence / intake 01</p>
        <h1>Keep the offer.<br /><em>Challenge the guess.</em></h1>
        <p class="intro-copy">
          Upload a supplier export. New structures request a human-confirmed mapping; repeat structures become deterministic data processing.
        </p>
        <dl class="rule-list">
          <div><dt>01</dt><dd>Supplier source stays traceable</dd></div>
          <div><dt>02</dt><dd>Model work is measured, never assumed</dd></div>
          <div><dt>03</dt><dd>Review is the acceptance boundary</dd></div>
        </dl>
      </div>

      <section class="intake-card" aria-labelledby="intake-title">
        <div class="card-kicker"><span class="live-dot"></span> JSON intake enabled</div>
        <h2 id="intake-title">Bring in a supplier export</h2>
        <p>Start with a JSON file. PDF, email, and OCR paths enter the same ledger in later stages.</p>
        <input ref="fileInput" class="visually-hidden" type="file" accept="application/json,.json" @change="chooseFile" />
        <button class="upload-zone" :disabled="busy" @click="fileInput?.click()">
          <span class="upload-icon">↑</span>
          <span><strong>{{ busy ? 'Reading the structure…' : 'Select supplier JSON' }}</strong><small>Maximum 5 MB · signature checked</small></span>
        </button>
        <p class="quiet-note">Try <code>sanova_offer_export_2026-08-03.json</code> from the supplied corpus.</p>
      </section>

      <section class="ledger-card" aria-live="polite">
        <div class="ledger-heading">
          <div>
            <p class="eyebrow">Current intake</p>
            <h2>{{ selectedDocument?.filename ?? 'No source selected' }}</h2>
          </div>
          <span class="status-badge" :data-status="selectedDocument?.status ?? 'idle'">{{ statusLabel }}</span>
        </div>

        <p v-if="errorMessage" class="error-message" role="alert">{{ errorMessage }}</p>
        <div v-else-if="!selectedDocument" class="empty-state">A source ledger will appear here after upload.</div>

        <template v-else>
          <div class="metric-strip">
            <div><span>Source system</span><strong>{{ selectedDocument.source_system }}</strong></div>
            <div><span>Schema version</span><strong>{{ selectedDocument.schema_version }}</strong></div>
            <div><span>Semantic calls</span><strong>{{ selectedDocument.semantic_mapping_calls }}</strong></div>
          </div>

          <div v-if="selectedDocument.status === 'needs_mapping_confirmation'" class="confirmation-panel">
            <div>
              <p class="eyebrow">Human checkpoint</p>
              <h3>Confirm this source-to-canonical map</h3>
              <p>The recorded mapper proposed a structure. Confirmation makes only this supplier fingerprint reusable.</p>
            </div>
            <button class="primary-action" :disabled="busy" @click="confirm">Confirm mapping</button>
          </div>

          <div v-if="selectedDocument.status === 'needs_mapping_resolution'" class="confirmation-panel conflict-panel">
            <div>
              <p class="eyebrow">Safe stop</p>
              <h3>The source structure changed</h3>
              <p>No prior mapping was applied. A reviewer must resolve this schema before it can be processed.</p>
            </div>
          </div>

          <div v-if="selectedDocument.quotation" class="quotation-view">
            <div class="quote-summary">
              <div><span>Reference</span><strong>{{ selectedDocument.quotation.quotation_reference }}</strong></div>
              <div><span>Supplier</span><strong>{{ selectedDocument.quotation.supplier.name }}</strong></div>
              <div><span>Terms</span><strong>{{ selectedDocument.quotation.commercial_terms.incoterm }} {{ selectedDocument.quotation.commercial_terms.incoterm_named_place }}</strong></div>
            </div>
            <div class="table-wrap">
              <table>
                <thead><tr><th>Product</th><th>Pack</th><th>MOQ</th><th>Pack price</th><th>Evidence</th></tr></thead>
                <tbody>
                  <tr v-for="(item, index) in selectedDocument.quotation.line_items" :key="item.source_key ?? index">
                    <td><strong>{{ item.product.trade_name }}</strong><small>{{ item.product.inn.join(' · ') }}</small></td>
                    <td>{{ item.packaging.units_per_pack }} {{ item.packaging.unit_label }}<small>{{ item.packaging.primary_pack }}</small></td>
                    <td>{{ item.quantity.minimum_order_quantity }} {{ item.quantity.minimum_order_quantity_uom }}</td>
                    <td>{{ item.pricing.currency }} {{ item.pricing.pack_price }}</td>
                    <td><span class="evidence-chip">{{ item.evidence.length }} source links</span></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </template>
      </section>
    </section>

    <section v-else class="evaluation-layout">
      <div class="evaluation-heading">
        <div>
          <p class="eyebrow">Level 1 / module evaluation</p>
          <h1>Evidence over <em>plausibility.</em></h1>
          <p>Each run is persisted in SQLite with its rubric, case-level scores, and error analysis.</p>
        </div>
        <button class="primary-action" :disabled="busy" @click="evaluate">{{ busy ? 'Running…' : 'Run recorded evaluation' }}</button>
      </div>

      <div class="rubric-grid">
        <article v-for="rubric in evaluations?.cases[0]?.rubric ?? []" :key="rubric.id">
          <span class="rubric-number">{{ rubric.id.slice(0, 2).toUpperCase() }}</span>
          <h2>{{ rubric.label }}</h2>
          <p>{{ rubric.success_criterion }}</p>
        </article>
      </div>

      <section class="runs-card">
        <div class="ledger-heading"><div><p class="eyebrow">Stored run history</p><h2>Golden dataset results</h2></div></div>
        <p v-if="errorMessage" class="error-message" role="alert">{{ errorMessage }}</p>
        <div v-else-if="!evaluations?.runs.length" class="empty-state">No evaluation runs yet. The first run verifies the cold-to-warm mapping contract.</div>
        <div v-else class="run-list">
          <article v-for="run in evaluations.runs" :key="run.id" class="run-row">
            <div><span class="run-mode">{{ run.execution_mode }}</span><strong>{{ run.summary.passed }}/{{ run.summary.case_count }} cases passed</strong><small>{{ new Date(run.created_at).toLocaleString() }}</small></div>
            <div v-for="result in run.results" :key="result.case_id" class="score-cluster">
              <span :class="['result-status', result.status]">{{ result.status }}</span>
              <span>Fidelity {{ Math.round(Number(result.scores.canonical_fidelity) * 100) }}%</span>
              <span>Warm calls {{ result.scores.warm_mapping_calls }}</span>
              <span>Recorded cost ${{ result.scores.estimated_cost_usd }}</span>
            </div>
          </article>
        </div>
      </section>
    </section>
  </main>
</template>
