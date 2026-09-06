<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";

import { confirmMapping, eventStreamUrl, fetchDocument, fetchEvaluations, reviewDocument, runEvaluation, sourceDocumentUrl, uploadBatch, uploadDocument } from "@/api";
import type { BatchResponse, DocumentResponse, EvaluationsResponse } from "@/types";

type Tab = "review" | "evaluations";

const activeTab = ref<Tab>("review");
const documents = ref<DocumentResponse[]>([]);
const activeBatch = ref<BatchResponse | null>(null);
const evaluations = ref<EvaluationsResponse | null>(null);
const busy = ref(false);
const errorMessage = ref("");
const fileInput = ref<HTMLInputElement | null>(null);
const correctionValues = ref<Record<string, string>>({});
const correctionFields = ref<Record<string, string>>({});
const correctionNotes = ref<Record<string, string>>({});
const eventSources = new Map<string, EventSource>();

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
    if (files.length > 1) {
      const batch = await uploadBatch(files);
      activeBatch.value = batch;
      documents.value.push(...batch.documents);
      batch.documents.forEach((document) => watchDocument(document.id));
    } else {
      const doc = await uploadDocument(files[0]);
      documents.value.push(doc);
      watchDocument(doc.id);
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "Upload failed.";
  } finally {
    busy.value = false;
    input.value = "";
  }
}

function replaceDocument(nextDocument: DocumentResponse) {
  documents.value = documents.value.map((document) => (document.id === nextDocument.id ? nextDocument : document));
  if (activeBatch.value) {
    activeBatch.value.documents = activeBatch.value.documents.map((d) => (d.id === nextDocument.id ? nextDocument : d));
  }
}

function watchDocument(documentId: string) {
  if (typeof EventSource === "undefined" || eventSources.has(documentId)) return;
  const source = new EventSource(eventStreamUrl(documentId));
  source.addEventListener("processing", () => fetchDocument(documentId).then(replaceDocument).catch(() => undefined));
  eventSources.set(documentId, source);
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
  const key = lineIndex === undefined ? "" : correctionKey(document.id, lineIndex);
  const patches =
    action === "correct" && lineIndex !== undefined
      ? [{ path: correctionPath(document.id, lineIndex), value: correctionValues.value[key] ?? "" }]
      : [];
  try {
    replaceDocument(
      await reviewDocument(document.id, action, {
        request_id: `${document.id}:${document.quotation.revision}:${action}:${lineIndex ?? "doc"}`,
        expected_revision: document.quotation.revision,
        note: correctionNotes.value[key] || undefined,
        patches
      })
    );
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "Review action failed.";
  } finally {
    busy.value = false;
  }
}

onMounted(() => loadEvaluations().catch(() => undefined));
onBeforeUnmount(() => eventSources.forEach((source) => source.close()));
</script>

<template>
  <div class="app-shell">
    <header class="masthead">
      <span class="wordmark">AXMED</span>
      <nav aria-label="Workspaces">
        <button :class="{ active: activeTab === 'review' }" @click="activeTab = 'review'">Review</button>
        <button :class="{ active: activeTab === 'evaluations' }" @click="activeTab = 'evaluations'">Evaluation lab</button>
      </nav>
    </header>

    <section v-if="activeTab === 'review'" class="workspace">
      <div class="toolbar">
        <h1>Documents</h1>
        <input ref="fileInput" class="visually-hidden" type="file" accept="application/json,.json,message/rfc822,.eml,application/pdf,.pdf,image/png,.png,image/jpeg,.jpg,.jpeg" multiple @change="chooseFile" />
        <button class="primary-action" :disabled="busy" @click="fileInput?.click()">{{ busy ? "Ingesting…" : "Ingest" }}</button>
      </div>

      <div v-if="activeBatch" class="batch-summary">
        <span>Batch: {{ activeBatch.total_documents }} files ({{ activeBatch.documents.filter(d => d.status === 'needs_review').length }} ready for review, {{ activeBatch.documents.filter(d => d.status === 'failed').length }} failed)</span>
        <span class="status">{{ activeBatch.documents.filter(d => ['needs_review', 'approved', 'rejected', 'failed'].includes(d.status)).length }} / {{ activeBatch.total_documents }} processed</span>
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
        <div v-else-if="document.status === 'needs_semantic_extraction'" class="notice">
          <span>{{ document.filename }}</span><span class="status">queued</span>
        </div>
        <div v-else-if="document.status === 'needs_ocr' || document.status === 'semantic_extraction_running'" class="notice">
          <span>{{ document.filename }}</span><span class="status">{{ document.status === 'needs_ocr' ? 'OCR' : 'processing' }}</span>
        </div>
        <div v-else-if="document.status === 'failed'" class="notice notice-error">
          <span>{{ document.filename }} · {{ document.failure_reason || "Extraction failed" }}</span>
          <span class="status">failed</span>
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
                  <td>
                    <strong>{{ item.product.trade_name ?? "—" }}</strong>
                    <small>{{ item.product.inn.join(" · ") }}</small>
                    <small v-if="item.product.dosage_form">{{ [item.product.dosage_form, item.packaging.presentation].filter(Boolean).join(" · ") }}</small>
                  </td>
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
        <div class="empty-state">No documents.</div>
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
                <td>
                  <details>
                    <summary>{{ run.id.slice(0, 8) }}</summary>
                    <table class="evaluation-results">
                      <thead><tr><th>Case</th><th>Result</th><th>Fidelity</th><th>Failure</th></tr></thead>
                      <tbody>
                        <tr v-for="result in run.results" :key="result.case_id">
                          <td>{{ result.case_id }}</td>
                          <td>{{ result.status }}<small v-if="result.scores.model">{{ [result.scores.model, result.scores.prompt_version].filter(Boolean).join(" · ") }}</small></td>
                          <td>{{ result.scores.canonical_fidelity ?? "—" }}</td>
                          <td>{{ result.errors.join("; ") || "—" }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </details>
                </td>
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
  </div>
</template>
