<script setup lang="ts">
import { onMounted, ref } from "vue";

import { confirmMapping, fetchEvaluations, reviewDocument, runEvaluation, sourceDocumentUrl, uploadDocument } from "@/api";
import type { DocumentResponse, EvaluationsResponse } from "@/types";

type Tab = "review" | "evaluations";

const activeTab = ref<Tab>("review");
const documents = ref<DocumentResponse[]>([]);
const evaluations = ref<EvaluationsResponse | null>(null);
const busy = ref(false);
const errorMessage = ref("");
const fileInput = ref<HTMLInputElement | null>(null);
const correctionValues = ref<Record<string, string>>({});
const correctionFields = ref<Record<string, string>>({});
const correctionNotes = ref<Record<string, string>>({});

function correctionKey(documentId: string, lineIndex: number) {
  return `${documentId}:${lineIndex}`;
}

function correctionPath(documentId: string, lineIndex: number) {
  const field = correctionFields.value[correctionKey(documentId, lineIndex)] ?? "pricing.pack_price";
  return `line_items.${lineIndex}.${field}`;
}

function hasBlockingIssue(document: DocumentResponse) {
  return document.quotation?.review_issues.some((issue) => issue.severity === "error") ?? false;
}

function displayPrice(value: string | null | undefined) {
  if (value == null) return "—";
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric.toLocaleString(undefined, { maximumFractionDigits: 6 }) : value;
}

function priceEvidence(item: { evidence: Array<{ canonical_field: string; source_path?: string | null; extraction_method: string; confidence: string }> }) {
  return item.evidence.find((evidence) => evidence.canonical_field === "pricing.pack_price") ?? item.evidence[0];
}

function source(item: { evidence: Array<{ canonical_field: string; source_path?: string | null; extraction_method: string; confidence: string }> }) {
  const evidence = priceEvidence(item);
  return evidence?.source_path ?? evidence?.extraction_method ?? "—";
}

function confidence(item: { evidence: Array<{ canonical_field: string; source_path?: string | null; extraction_method: string; confidence: string }> }) {
  const value = priceEvidence(item)?.confidence;
  return value ? `${Math.round(Number(value) * 100)}%` : "—";
}

async function loadEvaluations() {
  evaluations.value = await fetchEvaluations();
}

async function chooseFile(event: Event) {
  const input = event.target as HTMLInputElement;
  const files = Array.from(input.files ?? []);
  if (!files.length) return;
  busy.value = true;
  errorMessage.value = "";
  try {
    const results = await Promise.allSettled(files.map(uploadDocument));
    const accepted = results.flatMap((result) => (result.status === "fulfilled" ? [result.value] : []));
    const failures = results
      .filter((result): result is PromiseRejectedResult => result.status === "rejected")
      .map((result) => (result.reason instanceof Error ? result.reason.message : "Upload failed."));
    documents.value.push(...accepted);
    if (failures.length) {
      errorMessage.value = failures.join(" ");
    }
  } finally {
    busy.value = false;
    input.value = "";
  }
}

function replaceDocument(nextDocument: DocumentResponse) {
  documents.value = documents.value.map((document) => (document.id === nextDocument.id ? nextDocument : document));
}

async function confirm(document: DocumentResponse) {
  busy.value = true;
  errorMessage.value = "";
  try {
    replaceDocument(await confirmMapping(document.id));
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "Confirmation failed.";
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

async function decide(document: DocumentResponse, action: "approve" | "reject" | "correct", lineIndex?: number) {
  if (!document.quotation) return;
  busy.value = true;
  errorMessage.value = "";
  try {
    replaceDocument(await reviewDocument(document.id, action, {
      request_id: `${action}-${crypto.randomUUID()}`,
      expected_revision: document.quotation.revision,
      note: correctionNotes.value[document.id] || undefined,
      patches:
        action === "correct" && lineIndex !== undefined
          ? [
              {
                path: correctionPath(document.id, lineIndex),
                value: correctionValues.value[correctionKey(document.id, lineIndex)]
              }
            ]
          : undefined
    }));
    delete correctionValues.value[correctionKey(document.id, lineIndex ?? 0)];
    delete correctionFields.value[correctionKey(document.id, lineIndex ?? 0)];
    delete correctionNotes.value[document.id];
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "Review failed.";
  } finally {
    busy.value = false;
  }
}

onMounted(() => loadEvaluations().catch(() => undefined));
</script>

<template>
  <main class="app-shell">
    <header class="masthead">
      <span class="wordmark">AXMED</span>
      <nav aria-label="Sections">
        <button :class="{ active: activeTab === 'review' }" @click="activeTab = 'review'">Review</button>
        <button :class="{ active: activeTab === 'evaluations' }" @click="activeTab = 'evaluations'">Evaluation lab</button>
      </nav>
    </header>

    <section v-if="activeTab === 'review'" class="workspace">
      <div class="toolbar">
        <h1>Documents</h1>
        <input ref="fileInput" class="visually-hidden" type="file" accept="application/json,.json" multiple @change="chooseFile" />
        <button class="primary-action" :disabled="busy" @click="fileInput?.click()">{{ busy ? "Ingesting…" : "Ingest JSON" }}</button>
      </div>

      <p v-if="errorMessage" class="error-message" role="alert">{{ errorMessage }}</p>

      <section v-for="document in documents" :key="document.id" class="document-group">
        <div v-if="document.status === 'needs_mapping_confirmation'" class="notice">
          <span>{{ document.filename }} · new mapping</span>
          <button class="primary-action" :disabled="busy" @click="confirm(document)">Confirm map</button>
        </div>
        <div v-else-if="document.status === 'needs_mapping_resolution'" class="notice notice-error">
          {{ document.filename }} · changed source structure
        </div>

        <section v-if="document.quotation" class="panel">
          <div class="panel-header">
            <div>
              <h2>{{ document.filename }}</h2>
              <span class="metadata">{{ document.source_system }} · {{ document.schema_version }}</span>
            </div>
            <span class="status">{{ document.quotation.review_status }} · v{{ document.quotation.revision }}</span>
          </div>

          <div class="table-wrap">
            <table>
              <thead>
                <tr><th>Product</th><th>Quantity</th><th>Quoted</th><th>Derived</th><th>Source</th><th>Confidence</th><th>Issue</th><th>Review</th><th>Action</th></tr>
              </thead>
              <tbody>
                <tr v-for="(item, index) in document.quotation.line_items" :key="item.source_key ?? index">
                  <td><strong>{{ item.product.trade_name ?? "—" }}</strong><small>{{ item.product.inn.join(" · ") }}</small></td>
                  <td>{{ item.quantity.minimum_order_quantity ?? "—" }} {{ item.quantity.minimum_order_quantity_uom }}</td>
                  <td>{{ item.pricing.currency }} {{ displayPrice(item.pricing.quoted_price.amount) }} / {{ item.pricing.quoted_price.uom }}</td>
                  <td>
                    {{ item.pricing.currency }} {{ displayPrice(item.pricing.normalized_price.amount) }} / {{ item.pricing.normalized_price.uom }}
                    <small>{{ item.pricing.normalized_price.calculation }}</small>
                  </td>
                  <td>
                    <a :href="sourceDocumentUrl(document.id)" target="_blank" rel="noreferrer">{{ source(item) }}</a>
                  </td>
                  <td>{{ confidence(item) }}</td>
                  <td>
                    <span v-for="issue in document.quotation.review_issues.filter((issue) => issue.field_path.startsWith(`line_items[${index}]`))" :key="issue.code" class="issue">
                      {{ issue.message }}
                    </span>
                    <span v-if="!document.quotation.review_issues.some((issue) => issue.field_path.startsWith(`line_items[${index}]`))">—</span>
                  </td>
                  <td>{{ document.quotation.review_status }}</td>
                  <td>
                    <select v-model="correctionFields[correctionKey(document.id, index)]" aria-label="Correction field">
                      <option value="pricing.pack_price">Pack price</option>
                      <option value="quantity.minimum_order_quantity">MOQ</option>
                      <option value="packaging.units_per_pack">Units / pack</option>
                    </select>
                    <input v-model="correctionValues[correctionKey(document.id, index)]" :aria-label="`Correction value for ${item.product.trade_name ?? index}`" placeholder="Value" inputmode="decimal" />
                    <button class="table-action" :disabled="busy || !correctionValues[correctionKey(document.id, index)]" @click="decide(document, 'correct', index)">Correct</button>
                  </td>
                </tr>
              </tbody>
              <tfoot v-if="document.status === 'needs_review'">
                <tr>
                  <td colspan="9">
                    <div class="table-review">
                      <span v-if="hasBlockingIssue(document)" class="issue">Resolve issues before approval.</span>
                      <input v-model="correctionNotes[document.id]" :aria-label="`Review note for ${document.filename}`" placeholder="Note" />
                      <button :disabled="busy || hasBlockingIssue(document)" @click="decide(document, 'approve')">Approve</button>
                      <button :disabled="busy" @click="decide(document, 'reject')">Reject</button>
                    </div>
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        </section>
      </section>

      <section v-if="!documents.length" class="panel">
        <div class="empty-state">Ingest JSON files to view extracted offers.</div>
      </section>
    </section>

    <section v-else class="workspace">
      <div class="toolbar">
        <h1>Evaluations</h1>
        <button class="primary-action" :disabled="busy" @click="evaluate">{{ busy ? "Running…" : "Run" }}</button>
      </div>
      <p v-if="errorMessage" class="error-message" role="alert">{{ errorMessage }}</p>
      <section class="panel">
        <div class="table-wrap">
          <table>
            <thead><tr><th>Run</th><th>Result</th><th>Mode</th><th>Time</th></tr></thead>
            <tbody v-if="evaluations?.runs.length">
              <tr v-for="run in evaluations.runs" :key="run.id">
                <td>{{ run.id }}</td>
                <td>{{ run.summary.passed }}/{{ run.summary.case_count }} passed</td>
                <td>{{ run.execution_mode }}</td>
                <td>{{ new Date(run.created_at).toLocaleString() }}</td>
              </tr>
            </tbody>
            <tbody v-else><tr><td colspan="4" class="empty-state">No evaluation runs.</td></tr></tbody>
          </table>
        </div>
      </section>
    </section>
  </main>
</template>
