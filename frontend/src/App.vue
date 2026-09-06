<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import { confirmMapping, eventStreamUrl, fetchDocument, fetchDocuments, reviewDocument, sourceDocumentUrl, uploadBatch, uploadDocument } from "@/api";
import type { BatchResponse, DocumentResponse, LineItem } from "@/types";

const documents = ref<DocumentResponse[]>([]);
const activeBatch = ref<BatchResponse | null>(null);
const selectedDocumentId = ref<string | null>(null);
const selectedLineIndex = ref(0);
const busy = ref(false);
const errorMessage = ref("");
const fileInput = ref<HTMLInputElement | null>(null);
const correctionValues = ref<Record<string, string>>({});
const correctionFields = ref<Record<string, string>>({});
const correctionNotes = ref<Record<string, string>>({});
const eventSources = new Map<string, EventSource>();

const selectedDocument = computed(() => documents.value.find((document) => document.id === selectedDocumentId.value) ?? null);
const selectedLine = computed(() => selectedDocument.value?.quotation?.line_items[selectedLineIndex.value] ?? null);

function correctionKey(documentId: string, lineIndex: number) { return `${documentId}:${lineIndex}`; }

function correctionPath(documentId: string, lineIndex: number) {
  const field = correctionFields.value[correctionKey(documentId, lineIndex)] ?? "pricing.pack_price";
  return `line_items.${lineIndex}.${field}`;
}

function hasBlockingIssue(document: DocumentResponse) { return document.quotation?.review_issues.some((issue) => issue.severity === "error") ?? false; }

function displayValue(value: string | number | boolean | null | undefined) {
  if (value == null || value === "") return "—";
  if (typeof value === "string" && /^\d{4,}$/.test(value)) return Number(value).toLocaleString();
  return String(value);
}

function displayPrice(value: string | null | undefined) {
  if (value == null) return "—";
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric.toLocaleString(undefined, { maximumFractionDigits: 6 }) : value;
}

function additionalDetails(item: LineItem) {
  const regulatory = item.regulatory;
  const parts = [
    item.packaging.packs_per_shipper != null ? `${item.packaging.packs_per_shipper} packs / shipper` : null,
    item.supply.minimum_remaining_shelf_life_percent != null ? `min shelf ${item.supply.minimum_remaining_shelf_life_percent}%` : null,
    regulatory?.who_prequalified == null ? null : regulatory.who_prequalified ? `WHO prequalified${regulatory.who_pq_reference ? ` · ${regulatory.who_pq_reference}` : ""}` : "WHO not prequalified",
    regulatory?.registered_markets?.length ? `markets: ${regulatory.registered_markets.join(", ")}` : null,
    item.pricing.price_tiers?.length ? `${item.pricing.price_tiers.length} price tiers` : null,
    item.pricing.adjustments?.length ? `${item.pricing.adjustments.length} adjustments` : null,
  ];
  return parts.filter(Boolean).join(" · ") || "—";
}

function documentConfidence(document: DocumentResponse) {
  const values = document.quotation?.line_items.flatMap((item) => item.evidence.map((evidence) => Number(evidence.confidence))) ?? [];
  return values.length ? `${Math.round(Math.min(...values) * 100)}%` : "—";
}

function documentIssueCount(document: DocumentResponse) { return document.quotation?.review_issues.length ?? 0; }

function statusLabel(document: DocumentResponse) {
  if (document.status === "needs_review") return document.quotation ? `${document.quotation.review_status} · v${document.quotation.revision}` : "Ready for review";
  if (document.status === "needs_mapping_confirmation") return "Mapping check";
  if (document.status === "semantic_extraction_running") return "Processing";
  if (document.status === "needs_ocr") return "OCR required";
  return document.status.replaceAll("_", " ");
}

function openDocument(document: DocumentResponse) { selectedDocumentId.value = document.id; selectedLineIndex.value = 0; }
function closeDocument() { selectedDocumentId.value = null; }

async function loadDocuments() { documents.value = await fetchDocuments(); }

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
      documents.value = [...batch.documents, ...documents.value];
      batch.documents.forEach((document) => watchDocument(document.id));
    } else {
      const doc = await uploadDocument(files[0]);
      documents.value = [doc, ...documents.value.filter((document) => document.id !== doc.id)];
      watchDocument(doc.id);
      openDocument(doc);
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
  if (activeBatch.value) activeBatch.value.documents = activeBatch.value.documents.map((document) => (document.id === nextDocument.id ? nextDocument : document));
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
  try { replaceDocument(await confirmMapping(document.id)); }
  catch (error) { errorMessage.value = error instanceof Error ? error.message : "Confirmation failed."; }
  finally { busy.value = false; }
}

async function decide(document: DocumentResponse, action: "approve" | "reject" | "correct", lineIndex?: number) {
  if (!document.quotation) return;
  busy.value = true;
  errorMessage.value = "";
  const key = lineIndex === undefined ? "" : correctionKey(document.id, lineIndex);
  const patches = action === "correct" && lineIndex !== undefined ? [{ path: correctionPath(document.id, lineIndex), value: correctionValues.value[key] ?? "" }] : [];
  try {
    replaceDocument(await reviewDocument(document.id, action, {
      request_id: `${document.id}:${document.quotation.revision}:${action}:${lineIndex ?? "document"}`,
      expected_revision: document.quotation.revision,
      note: correctionNotes.value[key] || undefined,
      patches
    }));
  } catch (error) { errorMessage.value = error instanceof Error ? error.message : "Review action failed."; }
  finally { busy.value = false; }
}

function evidenceFor(item: LineItem, field: string) { return item.evidence.find((evidence) => evidence.canonical_field === field) ?? item.evidence[0]; }
function confidenceFor(item: LineItem, field: string) { const value = evidenceFor(item, field)?.confidence; return value ? `${Math.round(Number(value) * 100)}%` : "—"; }

onMounted(() => loadDocuments().catch(() => undefined));
onBeforeUnmount(() => eventSources.forEach((source) => source.close()));
</script>

<template>
  <div class="min-h-screen bg-[#f4f6f1] text-[#173b38]">
    <header class="border-b border-[#dce5de] bg-white">
      <div class="mx-auto flex h-16 max-w-[1500px] items-center justify-between px-5 sm:px-8 lg:px-12">
        <div class="flex items-center gap-8"><span class="text-sm font-black tracking-[0.28em] text-[#123b37]">AXMED</span><span class="border-l border-[#dce5de] pl-8 text-sm font-semibold text-[#55706b]">Review desk</span></div>
        <span class="hidden text-xs font-bold uppercase tracking-[0.2em] text-[#8aa09a] sm:inline">Supplier intelligence</span>
      </div>
    </header>

    <main class="mx-auto max-w-[1500px] px-5 py-8 sm:px-8 lg:px-12 lg:py-12">
      <div v-if="!selectedDocument" class="space-y-8">
        <section class="flex flex-col justify-between gap-6 sm:flex-row sm:items-end">
          <div><p class="mb-3 text-xs font-black uppercase tracking-[0.22em] text-[#d46537]">Home</p><h1 class="text-4xl font-black tracking-[-0.05em] text-[#123b37] sm:text-5xl">Your sources, at a glance.</h1><p class="mt-3 max-w-2xl text-base leading-7 text-[#617a74]">Review extracted supplier offers, resolve issues, and open any source for its full product breakdown.</p></div>
          <div><input ref="fileInput" class="sr-only" type="file" accept="application/json,.json,message/rfc822,.eml,application/pdf,.pdf,image/png,.png,image/jpeg,.jpg,.jpeg" multiple @change="chooseFile" /><button class="rounded-lg bg-[#123b37] px-5 py-3 text-sm font-bold text-white shadow-[0_8px_18px_rgba(18,59,55,0.16)] transition hover:bg-[#1b514a] disabled:cursor-wait disabled:opacity-60" :disabled="busy" @click="fileInput?.click()">{{ busy ? "Ingesting…" : "Ingest source" }}</button></div>
        </section>

        <section class="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div class="rounded-xl border border-[#dce5de] bg-white p-4"><p class="text-xs font-bold uppercase tracking-[0.14em] text-[#8aa09a]">Sources</p><p class="mt-2 text-2xl font-black text-[#123b37]">{{ documents.length }}</p></div>
          <div class="rounded-xl border border-[#dce5de] bg-white p-4"><p class="text-xs font-bold uppercase tracking-[0.14em] text-[#8aa09a]">Ready</p><p class="mt-2 text-2xl font-black text-[#2c765d]">{{ documents.filter(d => d.status === 'needs_review').length }}</p></div>
          <div class="rounded-xl border border-[#dce5de] bg-white p-4"><p class="text-xs font-bold uppercase tracking-[0.14em] text-[#8aa09a]">Needs attention</p><p class="mt-2 text-2xl font-black text-[#c45e31]">{{ documents.filter(d => documentIssueCount(d) > 0 || d.status === 'failed').length }}</p></div>
          <div class="rounded-xl border border-[#dce5de] bg-white p-4"><p class="text-xs font-bold uppercase tracking-[0.14em] text-[#8aa09a]">Reviewed</p><p class="mt-2 text-2xl font-black text-[#123b37]">{{ documents.filter(d => ['approved', 'rejected'].includes(d.quotation?.review_status ?? '')).length }}</p></div>
        </section>

        <div v-if="activeBatch" class="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[#c6dfd5] bg-[#edf8f2] px-5 py-4 text-sm font-semibold text-[#27664d]"><span>Batch: {{ activeBatch.total_documents }} sources</span><span>{{ activeBatch.documents.filter(d => ['needs_review', 'approved', 'rejected', 'failed'].includes(d.status)).length }} / {{ activeBatch.total_documents }} processed</span></div>
        <p v-if="errorMessage" class="rounded-lg border border-[#efc7bd] bg-[#fff1ee] px-4 py-3 text-sm text-[#9d3827]" role="alert">{{ errorMessage }}</p>

        <section class="overflow-hidden rounded-2xl border border-[#dce5de] bg-white shadow-[0_12px_40px_rgba(32,69,60,0.05)]">
          <div class="border-b border-[#e8eeea] px-5 py-5 sm:px-6"><h2 class="text-lg font-black text-[#123b37]">Uploaded sources</h2><p class="mt-1 text-sm text-[#789089]">Supplier-level review status and extraction health.</p></div>
          <div v-if="documents.length" class="divide-y divide-[#e8eeea]"><button v-for="document in documents" :key="document.id" class="group grid w-full gap-4 px-5 py-5 text-left transition hover:bg-[#f8faf7] sm:grid-cols-[minmax(0,2fr)_minmax(170px,1fr)_auto] sm:items-center sm:px-6" @click="openDocument(document)"><div class="min-w-0"><div class="flex items-center gap-3"><span class="truncate text-base font-black text-[#173b38]">{{ document.filename }}</span><span class="shrink-0 rounded-full bg-[#edf3ee] px-2.5 py-1 text-[11px] font-black uppercase tracking-[0.08em] text-[#39705a]">{{ statusLabel(document) }}</span></div><p class="mt-2 text-sm text-[#6c827c]">{{ document.quotation?.supplier.name || "Supplier pending extraction" }} <span class="px-1 text-[#b3c1bc]">·</span> {{ document.quotation?.quotation_reference || document.source_system || "Source pending" }}</p></div><div class="flex gap-7 text-sm text-[#54706a]"><span><span class="block text-[10px] font-black uppercase tracking-[0.14em] text-[#9aaba5]">Confidence</span><span class="mt-1 block font-bold">{{ documentConfidence(document) }}</span></span><span><span class="block text-[10px] font-black uppercase tracking-[0.14em] text-[#9aaba5]">Issues</span><span class="mt-1 block font-bold" :class="documentIssueCount(document) ? 'text-[#c45e31]' : 'text-[#39705a]'">{{ documentIssueCount(document) || "None" }}</span></span></div><span class="text-xl text-[#91a7a0] transition group-hover:translate-x-1 group-hover:text-[#d46537]">→</span></button></div>
          <div v-else class="px-6 py-20 text-center"><p class="text-lg font-black text-[#335853]">No sources yet.</p><p class="mt-2 text-sm text-[#789089]">Ingest a PDF, email, image, or JSON offer to begin review.</p></div>
        </section>
      </div>

      <div v-else class="space-y-7">
        <button class="text-sm font-bold text-[#5f7a73] transition hover:text-[#d46537]" @click="closeDocument">← Back to sources</button>
        <section class="flex flex-col justify-between gap-6 border-b border-[#dce5de] pb-7 lg:flex-row lg:items-end"><div><p class="mb-3 text-xs font-black uppercase tracking-[0.2em] text-[#d46537]">Source detail</p><h1 class="max-w-4xl text-3xl font-black tracking-[-0.04em] text-[#123b37] sm:text-4xl">{{ selectedDocument.filename }}</h1><div class="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-sm text-[#637a74]"><span>{{ selectedDocument.quotation?.supplier.name || "Supplier pending" }}</span><span>{{ selectedDocument.quotation?.quotation_reference || "No quotation reference" }}</span><span>{{ selectedDocument.parsed_summary?.page_count ? `${selectedDocument.parsed_summary.page_count} pages` : selectedDocument.source_system || "Source" }}</span></div></div><div class="flex flex-wrap items-center gap-3"><span class="rounded-full bg-[#e8f2eb] px-3 py-1.5 text-xs font-black uppercase tracking-[0.1em] text-[#39705a]">{{ statusLabel(selectedDocument) }}</span><a class="text-sm font-bold text-[#39705a] underline decoration-[#b7cec1] underline-offset-4 hover:text-[#d46537]" :href="sourceDocumentUrl(selectedDocument.id)" target="_blank" rel="noreferrer">Open original</a></div></section>
        <div v-if="selectedDocument.status === 'needs_mapping_confirmation'" class="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-[#edd4b7] bg-[#fff6e9] px-5 py-4 text-sm text-[#81542f]"><span>New source structure detected. Confirm the proposed mapping before review.</span><button class="rounded-md bg-[#123b37] px-4 py-2 text-xs font-bold text-white" :disabled="busy" @click="confirm(selectedDocument)">Confirm mapping</button></div>
        <p v-if="errorMessage" class="rounded-lg border border-[#efc7bd] bg-[#fff1ee] px-4 py-3 text-sm text-[#9d3827]" role="alert">{{ errorMessage }}</p>

        <section v-if="selectedDocument.quotation" class="overflow-hidden rounded-2xl border border-[#dce5de] bg-white shadow-[0_12px_40px_rgba(32,69,60,0.05)]"><div class="flex flex-wrap items-center justify-between gap-3 border-b border-[#e8eeea] px-5 py-5 sm:px-6"><div><h2 class="text-lg font-black text-[#123b37]">Product breakdown</h2><p class="mt-1 text-sm text-[#789089]">{{ selectedDocument.quotation.line_items.length }} extracted line items · quantities are shown from the quoted source volume.</p></div><span class="text-sm font-bold text-[#668079]">Confidence {{ documentConfidence(selectedDocument) }}</span></div><div class="overflow-x-auto"><table class="min-w-[920px] w-full text-left text-sm"><thead class="bg-[#f8faf7] text-[10px] font-black uppercase tracking-[0.16em] text-[#81958f]"><tr><th class="px-5 py-4">Product</th><th class="px-4 py-4">Quantity</th><th class="px-4 py-4">Quoted</th><th class="px-4 py-4">Pack</th><th class="px-4 py-4">Supply</th><th class="px-4 py-4">Confidence</th><th class="px-4 py-4">Issue</th><th class="px-4 py-4"></th></tr></thead><tbody class="divide-y divide-[#e8eeea]"><tr v-for="(item, index) in selectedDocument.quotation.line_items" :key="item.source_key ?? index" class="align-top transition hover:bg-[#fbfcfa]" :class="selectedLineIndex === index ? 'bg-[#f4f9f5]' : ''"><td class="px-5 py-5"><button class="text-left" @click="selectedLineIndex = index"><span class="block font-black text-[#173b38]">{{ item.product.trade_name || "Unnamed product" }}</span><span class="mt-1 block text-xs text-[#789089]">{{ item.product.inn.join(" · ") || "INN not provided" }}</span><span class="mt-1 block text-xs text-[#789089]">{{ [item.product.dosage_form, item.packaging.presentation].filter(Boolean).join(" · ") || "Form not provided" }}</span></button></td><td class="px-4 py-5 font-bold text-[#315a53]">{{ displayValue(item.quantity.quoted_quantity) }} <span class="font-normal text-[#789089]">{{ item.quantity.quoted_quantity_uom || "" }}</span><span v-if="item.quantity.minimum_order_quantity" class="mt-1 block text-xs font-normal text-[#789089]">MOQ {{ item.quantity.minimum_order_quantity }} {{ item.quantity.minimum_order_quantity_uom }}</span></td><td class="px-4 py-5 font-bold text-[#315a53]">{{ item.pricing.currency }} {{ displayPrice(item.pricing.quoted_price.amount) }}<span class="font-normal text-[#789089]"> / {{ item.pricing.quoted_price.uom || "unit" }}</span><span class="mt-1 block text-xs font-normal text-[#789089]">Extended {{ displayPrice(item.pricing.extended_price) }}</span></td><td class="px-4 py-5 text-[#54706a]"><span class="block">{{ item.packaging.primary_pack || "—" }}</span><span class="mt-1 block text-xs">{{ item.packaging.units_per_pack ? `${item.packaging.units_per_pack} ${item.packaging.unit_label || "units"}` : item.packaging.unit_label || "" }}</span></td><td class="px-4 py-5 text-[#54706a]">{{ item.supply.lead_time_days ? `${item.supply.lead_time_days} days` : "—" }}<span v-if="item.supply.shelf_life_months" class="mt-1 block text-xs">{{ item.supply.shelf_life_months }} mo shelf</span></td><td class="px-4 py-5 font-bold text-[#39705a]">{{ confidenceFor(item, "product.trade_name") }}</td><td class="px-4 py-5"><span v-for="issue in selectedDocument.quotation.review_issues.filter((issue) => issue.field_path.startsWith(`line_items[${index}]`))" :key="issue.code" class="block max-w-[160px] text-xs text-[#b34d31]">{{ issue.message }}</span><span v-if="!selectedDocument.quotation.review_issues.some((issue) => issue.field_path.startsWith(`line_items[${index}]`))" class="text-[#9aaba5]">—</span></td><td class="px-4 py-5"><button class="font-bold text-[#39705a] hover:text-[#d46537]" @click="selectedLineIndex = index">View →</button></td></tr></tbody></table></div></section>

        <section v-if="selectedLine" class="grid gap-6 lg:grid-cols-[1.15fr_0.85fr]"><div class="rounded-2xl border border-[#dce5de] bg-white p-5 shadow-[0_12px_40px_rgba(32,69,60,0.04)] sm:p-6"><div class="mb-5 flex items-start justify-between gap-4"><div><p class="text-xs font-black uppercase tracking-[0.18em] text-[#d46537]">Product detail</p><h2 class="mt-2 text-2xl font-black tracking-[-0.03em] text-[#123b37]">{{ selectedLine.product.trade_name || "Unnamed product" }}</h2></div><span class="rounded-full bg-[#edf3ee] px-3 py-1 text-xs font-bold text-[#39705a]">Line {{ selectedLineIndex + 1 }}</span></div><div class="grid gap-5 sm:grid-cols-2"><div><p class="text-[10px] font-black uppercase tracking-[0.14em] text-[#8aa09a]">Active ingredients</p><p class="mt-2 text-sm font-bold leading-6 text-[#315a53]">{{ selectedLine.product.inn.join(" · ") || "—" }}</p></div><div><p class="text-[10px] font-black uppercase tracking-[0.14em] text-[#8aa09a]">Strength</p><p class="mt-2 text-sm font-bold leading-6 text-[#315a53]">{{ (selectedLine.product.strength ?? []).map(s => `${displayValue(s.value)} ${displayValue(s.unit)}${s.per_value ? ` / ${s.per_value} ${s.per_unit}` : ''}`).join(" · ") || "—" }}</p></div><div><p class="text-[10px] font-black uppercase tracking-[0.14em] text-[#8aa09a]">Dosage form / route</p><p class="mt-2 text-sm font-bold leading-6 text-[#315a53]">{{ [selectedLine.product.dosage_form, selectedLine.product.route].filter(Boolean).join(" · ") || "—" }}</p></div><div><p class="text-[10px] font-black uppercase tracking-[0.14em] text-[#8aa09a]">Manufacturer / origin</p><p class="mt-2 text-sm font-bold leading-6 text-[#315a53]">{{ [selectedLine.product.manufacturer, selectedLine.product.country_of_origin].filter(Boolean).join(" · ") || "—" }}</p></div><div><p class="text-[10px] font-black uppercase tracking-[0.14em] text-[#8aa09a]">Packaging</p><p class="mt-2 text-sm font-bold leading-6 text-[#315a53]">{{ [selectedLine.packaging.description, selectedLine.packaging.primary_pack, selectedLine.packaging.units_per_pack ? `${selectedLine.packaging.units_per_pack} ${selectedLine.packaging.unit_label || 'units'}` : null].filter(Boolean).join(" · ") || "—" }}</p></div><div><p class="text-[10px] font-black uppercase tracking-[0.14em] text-[#8aa09a]">Quoted quantity</p><p class="mt-2 text-sm font-bold leading-6 text-[#315a53]">{{ displayValue(selectedLine.quantity.quoted_quantity) }} {{ selectedLine.quantity.quoted_quantity_uom || "" }}</p></div><div><p class="text-[10px] font-black uppercase tracking-[0.14em] text-[#8aa09a]">MOQ / basis</p><p class="mt-2 text-sm font-bold leading-6 text-[#315a53]">{{ selectedLine.quantity.minimum_order_quantity ? `${selectedLine.quantity.minimum_order_quantity} ${selectedLine.quantity.minimum_order_quantity_uom || ''}` : "—" }}<span v-if="selectedLine.quantity.quantity_basis" class="mt-1 block text-xs font-normal text-[#789089]">{{ selectedLine.quantity.quantity_basis }}</span></p></div><div><p class="text-[10px] font-black uppercase tracking-[0.14em] text-[#8aa09a]">Quoted / normalized price</p><p class="mt-2 text-sm font-bold leading-6 text-[#315a53]">{{ selectedLine.pricing.currency }} {{ displayPrice(selectedLine.pricing.quoted_price.amount) }} / {{ selectedLine.pricing.quoted_price.uom || "unit" }}<span class="mt-1 block text-xs font-normal text-[#789089]">{{ displayPrice(selectedLine.pricing.normalized_price.amount) }} / {{ selectedLine.pricing.normalized_price.uom || "unit" }}{{ selectedLine.pricing.normalized_price.calculation ? ` · ${selectedLine.pricing.normalized_price.calculation}` : '' }}</span></p></div><div><p class="text-[10px] font-black uppercase tracking-[0.14em] text-[#8aa09a]">Discount / extended</p><p class="mt-2 text-sm font-bold leading-6 text-[#315a53]">{{ selectedLine.pricing.discount ? `${selectedLine.pricing.discount}%` : "—" }}<span class="mt-1 block text-xs font-normal text-[#789089]">{{ displayPrice(selectedLine.pricing.extended_price) }}</span></p></div><div><p class="text-[10px] font-black uppercase tracking-[0.14em] text-[#8aa09a]">Lead time / shelf life</p><p class="mt-2 text-sm font-bold leading-6 text-[#315a53]">{{ selectedLine.supply.lead_time_days ? `${selectedLine.supply.lead_time_days} days` : "—" }}<span class="mt-1 block text-xs font-normal text-[#789089]">{{ selectedLine.supply.shelf_life_months ? `${selectedLine.supply.shelf_life_months} months` : "" }}</span></p></div><div><p class="text-[10px] font-black uppercase tracking-[0.14em] text-[#8aa09a]">Storage / cold chain</p><p class="mt-2 text-sm font-bold leading-6 text-[#315a53]">{{ [selectedLine.supply.storage_conditions, selectedLine.supply.cold_chain_required ? "Cold chain" : null].filter(Boolean).join(" · ") || "—" }}</p></div><div><p class="text-[10px] font-black uppercase tracking-[0.14em] text-[#8aa09a]">Regulatory / additional</p><p class="mt-2 text-sm font-bold leading-6 text-[#315a53]">{{ [ [selectedLine.regulatory?.regulatory_status, selectedLine.regulatory?.registration_reference, selectedLine.regulatory?.hs_code, selectedLine.regulatory?.atc_code].filter(Boolean).join(" · "), additionalDetails(selectedLine) ].filter(Boolean).join(" · ") || "—" }}</p></div></div></div><div class="space-y-6"><div class="rounded-2xl border border-[#dce5de] bg-white p-5 shadow-[0_12px_40px_rgba(32,69,60,0.04)] sm:p-6"><p class="text-xs font-black uppercase tracking-[0.18em] text-[#d46537]">Review this line</p><div class="mt-5 space-y-3"><select v-model="correctionFields[correctionKey(selectedDocument.id, selectedLineIndex)]" class="w-full rounded-md border border-[#cbd9d2] bg-white px-3 py-2.5 text-sm text-[#315a53]" aria-label="Correction field"><option value="pricing.pack_price">Pack price</option><option value="quantity.quoted_quantity">Quoted quantity</option><option value="quantity.minimum_order_quantity">MOQ</option><option value="packaging.units_per_pack">Units / pack</option></select><input v-model="correctionValues[correctionKey(selectedDocument.id, selectedLineIndex)]" class="w-full rounded-md border border-[#cbd9d2] px-3 py-2.5 text-sm" :aria-label="`Correction value for ${selectedLine.product.trade_name ?? selectedLineIndex}`" placeholder="Corrected value" inputmode="decimal" /><button class="w-full rounded-md border border-[#78958b] px-4 py-2.5 text-sm font-bold text-[#315a53] transition hover:border-[#d46537] hover:text-[#d46537] disabled:opacity-50" :disabled="busy || !correctionValues[correctionKey(selectedDocument.id, selectedLineIndex)]" @click="decide(selectedDocument, 'correct', selectedLineIndex)">Save correction</button></div></div><div v-if="selectedDocument.status === 'needs_review'" class="rounded-2xl border border-[#dce5de] bg-white p-5 shadow-[0_12px_40px_rgba(32,69,60,0.04)] sm:p-6"><p class="text-xs font-black uppercase tracking-[0.18em] text-[#d46537]">Source decision</p><input v-model="correctionNotes[selectedDocument.id]" class="mt-5 w-full rounded-md border border-[#cbd9d2] px-3 py-2.5 text-sm" :aria-label="`Review note for ${selectedDocument.filename}`" placeholder="Add a review note (optional)" /><p v-if="hasBlockingIssue(selectedDocument)" class="mt-3 text-xs text-[#b34d31]">Resolve error-level issues before approval.</p><div class="mt-4 flex gap-3"><button class="flex-1 rounded-md bg-[#123b37] px-4 py-2.5 text-sm font-bold text-white disabled:opacity-50" :disabled="busy || hasBlockingIssue(selectedDocument)" @click="decide(selectedDocument, 'approve')">Approve source</button><button class="rounded-md border border-[#d59d92] px-4 py-2.5 text-sm font-bold text-[#a54838]" :disabled="busy" @click="decide(selectedDocument, 'reject')">Reject</button></div></div></div></section>
      </div>
    </main>
  </div>
</template>
