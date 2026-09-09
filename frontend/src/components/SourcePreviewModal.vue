<script setup lang="ts">
/** In-platform preview for uploaded source files without forcing a download. */

import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";

const props = defineProps<{
  document: { id: string; filename: string } | null;
  sourceUrl: string;
}>();

const emit = defineEmits<{ (event: "close"): void }>();

const loading = ref(false);
const errorMessage = ref("");
const textContent = ref("");
const objectUrl = ref("");
const closeButton = ref<HTMLButtonElement | null>(null);
let abortController: AbortController | null = null;

const extension = computed(() => props.document?.filename.split(".").pop()?.toLowerCase() ?? "");
const isText = computed(() => ["json", "eml", "txt", "csv", "xml"].includes(extension.value));
const isImage = computed(() => ["png", "jpg", "jpeg", "gif", "webp"].includes(extension.value));
const isPdf = computed(() => extension.value === "pdf");

function releaseObjectUrl() {
  if (objectUrl.value) URL.revokeObjectURL(objectUrl.value);
  objectUrl.value = "";
}

async function loadPreview() {
  abortController?.abort();
  abortController = null;
  releaseObjectUrl();
  textContent.value = "";
  errorMessage.value = "";
  if (!props.document || !props.sourceUrl) return;

  loading.value = true;
  abortController = new AbortController();
  try {
    const response = await fetch(props.sourceUrl, { signal: abortController.signal });
    if (!response.ok) throw new Error("The source could not be loaded.");
    if (isText.value) {
      const raw = await response.text();
      if (extension.value === "json") {
        try {
          textContent.value = JSON.stringify(JSON.parse(raw), null, 2);
        } catch {
          textContent.value = raw;
        }
      } else {
        textContent.value = raw;
      }
    } else {
      objectUrl.value = URL.createObjectURL(await response.blob());
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") return;
    errorMessage.value = error instanceof Error ? error.message : "The source could not be loaded.";
  } finally {
    loading.value = false;
  }
}

function close() {
  emit("close");
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === "Escape") close();
}

watch(
  () => props.document,
  async (document) => {
    if (document) {
      window.addEventListener("keydown", handleKeydown);
      await nextTick();
      closeButton.value?.focus();
      await loadPreview();
    } else {
      window.removeEventListener("keydown", handleKeydown);
      abortController?.abort();
      releaseObjectUrl();
    }
  },
  { immediate: true }
);

onBeforeUnmount(() => {
  window.removeEventListener("keydown", handleKeydown);
  abortController?.abort();
  releaseObjectUrl();
});
</script>

<template>
  <Teleport to="body">
    <div
      v-if="document"
      class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/55 p-3 sm:p-6"
      role="presentation"
      @mousedown.self="close"
    >
      <section
        class="flex h-[min(92vh,900px)] w-full max-w-6xl flex-col overflow-hidden rounded-2xl border border-slate-300 bg-white shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="source-preview-title"
      >
        <header class="flex items-center justify-between gap-4 border-b border-slate-200 px-4 py-3 sm:px-5">
          <div class="min-w-0">
            <p class="text-[10px] font-bold uppercase tracking-[0.16em] text-slate-500">Source preview</p>
            <h2 id="source-preview-title" class="truncate text-sm font-bold text-slate-900">{{ document.filename }}</h2>
          </div>
          <button
            ref="closeButton"
            type="button"
            class="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-slate-300 text-slate-600 transition hover:bg-slate-100 hover:text-slate-950"
            aria-label="Close source preview"
            @click="close"
          >
            <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" d="M6 6l12 12M18 6 6 18" />
            </svg>
          </button>
        </header>

        <div class="min-h-0 flex-1 bg-slate-100">
          <div v-if="loading" class="flex h-full items-center justify-center text-sm font-semibold text-slate-600">
            Loading preview…
          </div>
          <div v-else-if="errorMessage" class="flex h-full items-center justify-center p-8 text-center">
            <div>
              <p class="text-sm font-bold text-slate-900">Preview unavailable</p>
              <p class="mt-1 text-xs text-slate-600">{{ errorMessage }}</p>
            </div>
          </div>
          <pre
            v-else-if="isText"
            class="h-full overflow-auto whitespace-pre-wrap break-words bg-[#101828] p-5 font-mono text-xs leading-6 text-slate-100 sm:p-7"
          >{{ textContent }}</pre>
          <img v-else-if="isImage && objectUrl" :src="objectUrl" :alt="document.filename" class="h-full w-full object-contain p-4" />
          <iframe v-else-if="isPdf && objectUrl" :src="objectUrl" :title="document.filename" class="h-full w-full border-0 bg-white"></iframe>
          <iframe v-else-if="objectUrl" :src="objectUrl" :title="document.filename" class="h-full w-full border-0 bg-white"></iframe>
        </div>
      </section>
    </div>
  </Teleport>
</template>
