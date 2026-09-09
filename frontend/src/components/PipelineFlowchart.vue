<script setup lang="ts">
/** Interactive draggable and zoomable flowchart canvas presenting the Axmed extraction architecture in clean Mermaid style. */

import { computed, onMounted, onUnmounted, ref } from "vue";

withDefaults(
  defineProps<{
    height?: string;
  }>(),
  {
    height: "620px",
  }
);

const containerRef = ref<HTMLDivElement | null>(null);

// Pan and zoom state
const zoom = ref(1);
const pan = ref({ x: 0, y: 0 });
const isDragging = ref(false);
const dragStart = ref({ x: 0, y: 0 });

const zoomPercent = computed(() => `${Math.round(zoom.value * 100)}%`);

function onMouseDown(e: MouseEvent) {
  if (e.button !== 0) return;
  isDragging.value = true;
  dragStart.value = {
    x: e.clientX - pan.value.x,
    y: e.clientY - pan.value.y,
  };
}

function onMouseMove(e: MouseEvent) {
  if (!isDragging.value) return;
  pan.value = {
    x: e.clientX - dragStart.value.x,
    y: e.clientY - dragStart.value.y,
  };
}

function stopDrag() {
  isDragging.value = false;
}

function onWheel(e: WheelEvent) {
  e.preventDefault();
  const zoomFactor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
  const newZoom = Math.min(Math.max(zoom.value * zoomFactor, 0.45), 2.8);
  if (newZoom === zoom.value) return;

  const container = containerRef.value;
  if (container) {
    const rect = container.getBoundingClientRect();
    const mouseX = e.clientX - rect.left - rect.width / 2;
    const mouseY = e.clientY - rect.top - rect.height / 2;
    const ratio = newZoom / zoom.value;
    pan.value = {
      x: mouseX - (mouseX - pan.value.x) * ratio,
      y: mouseY - (mouseY - pan.value.y) * ratio,
    };
  }
  zoom.value = newZoom;
}

// Touch event handling for mobile/pinch
let initialTouchDistance = 0;
let initialTouchZoom = 1;
let touchStartPan = { x: 0, y: 0 };
let touchStartPos = { x: 0, y: 0 };

function onTouchStart(e: TouchEvent) {
  if (e.touches.length === 1) {
    isDragging.value = true;
    touchStartPos = { x: e.touches[0].clientX, y: e.touches[0].clientY };
    touchStartPan = { ...pan.value };
  } else if (e.touches.length === 2) {
    isDragging.value = false;
    const dx = e.touches[0].clientX - e.touches[1].clientX;
    const dy = e.touches[0].clientY - e.touches[1].clientY;
    initialTouchDistance = Math.hypot(dx, dy);
    initialTouchZoom = zoom.value;
  }
}

function onTouchMove(e: TouchEvent) {
  if (e.touches.length === 1 && isDragging.value) {
    e.preventDefault();
    pan.value = {
      x: touchStartPan.x + (e.touches[0].clientX - touchStartPos.x),
      y: touchStartPan.y + (e.touches[0].clientY - touchStartPos.y),
    };
  } else if (e.touches.length === 2 && initialTouchDistance > 0) {
    e.preventDefault();
    const dx = e.touches[0].clientX - e.touches[1].clientX;
    const dy = e.touches[0].clientY - e.touches[1].clientY;
    const currentDistance = Math.hypot(dx, dy);
    const ratio = currentDistance / initialTouchDistance;
    zoom.value = Math.min(Math.max(initialTouchZoom * ratio, 0.45), 2.8);
  }
}

function onTouchEnd() {
  isDragging.value = false;
  initialTouchDistance = 0;
}

function zoomIn() {
  zoom.value = Math.min(zoom.value * 1.2, 2.8);
}

function zoomOut() {
  zoom.value = Math.max(zoom.value / 1.2, 0.45);
}

function resetView() {
  zoom.value = 1;
  pan.value = { x: 0, y: 0 };
}

onMounted(() => {
  window.addEventListener("mouseup", stopDrag);
});
onUnmounted(() => {
  window.removeEventListener("mouseup", stopDrag);
});
</script>

<template>
  <div class="relative overflow-hidden rounded-2xl border border-rule bg-slate-950 shadow-inner select-none">
    <!-- Floating Pan & Zoom Controls Toolbar -->
    <div class="absolute top-4 right-4 z-20 flex items-center gap-1 rounded-xl bg-slate-900/90 backdrop-blur-md border border-slate-700/80 p-1.5 shadow-2xl text-white">
      <button
        type="button"
        class="rounded-lg p-1.5 text-slate-300 hover:bg-slate-800 hover:text-white transition cursor-pointer"
        title="Zoom Out (Scroll down or click)"
        aria-label="Zoom Out"
        @click="zoomOut"
      >
        <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M20 12H4" />
        </svg>
      </button>

      <button
        type="button"
        class="min-w-[50px] px-1.5 py-0.5 font-mono text-[11px] font-bold text-slate-200 hover:text-sky-400 text-center transition cursor-pointer"
        title="Reset to 100%"
        @click="resetView"
      >
        {{ zoomPercent }}
      </button>

      <button
        type="button"
        class="rounded-lg p-1.5 text-slate-300 hover:bg-slate-800 hover:text-white transition cursor-pointer"
        title="Zoom In (Scroll up or click)"
        aria-label="Zoom In"
        @click="zoomIn"
      >
        <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
        </svg>
      </button>

      <div class="h-4 w-px bg-slate-700 mx-1"></div>

      <button
        type="button"
        class="rounded-lg px-2.5 py-1 text-xs font-semibold text-sky-400 hover:bg-slate-800 hover:text-sky-300 transition cursor-pointer"
        title="Reset pan and zoom"
        @click="resetView"
      >
        Reset
      </button>
    </div>

    <!-- Floating Interaction Hint -->
    <div class="absolute bottom-3 left-3 z-20 pointer-events-none hidden sm:flex items-center gap-2 rounded-lg bg-slate-900/80 backdrop-blur-xs border border-slate-800 px-3 py-1.5 text-[11px] text-slate-400">
      <span class="inline-block h-2 w-2 rounded-full bg-emerald-500 animate-pulse"></span>
      <span>Click & drag to pan &bull; Mouse wheel to zoom &bull; Pinch on touchpad</span>
    </div>

    <!-- Interactive Draggable / Zoomable Canvas Viewport -->
    <div
      ref="containerRef"
      class="w-full overflow-hidden flex items-center justify-center cursor-grab active:cursor-grabbing"
      :style="{ height }"
      @mousedown="onMouseDown"
      @mousemove="onMouseMove"
      @mouseup="stopDrag"
      @mouseleave="stopDrag"
      @wheel.prevent="onWheel"
      @touchstart="onTouchStart"
      @touchmove="onTouchMove"
      @touchend="onTouchEnd"
    >
      <!-- Transformed SVG Plane -->
      <div
        class="flex items-center justify-center p-6 sm:p-10 pointer-events-none"
        :style="{
          transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
          transformOrigin: 'center center',
          transition: isDragging ? 'none' : 'transform 0.12s cubic-bezier(0.16, 1, 0.3, 1)',
        }"
      >
        <svg
          class="w-[1060px] max-w-none h-auto pointer-events-auto"
          viewBox="0 0 1060 690"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          <defs>
            <!-- Arrowhead Markers -->
            <marker id="m-slate" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 1 L 8 5 L 0 9 z" fill="#64748B" />
            </marker>
            <marker id="m-sky" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 1 L 8 5 L 0 9 z" fill="#38BDF8" />
            </marker>
            <marker id="m-green" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 1 L 8 5 L 0 9 z" fill="#10B981" />
            </marker>
            <marker id="m-purple" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 1 L 8 5 L 0 9 z" fill="#A78BFA" />
            </marker>
            <marker id="m-amber" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 1 L 8 5 L 0 9 z" fill="#F59E0B" />
            </marker>
            <marker id="m-rose" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 1 L 8 5 L 0 9 z" fill="#F43F5E" />
            </marker>
          </defs>

          <!-- TOP LEGEND (Mermaid Style) -->
          <rect x="40" y="8" width="980" height="32" rx="8" fill="#1E293B" stroke="#334155" stroke-width="1" />
          <g transform="translate(65, 16)">
            <rect x="0" y="2" width="12" height="12" rx="3" fill="#2E1065" stroke="#A78BFA" stroke-width="1.5" />
            <text x="18" y="12" fill="#E2E8F0" font-size="10.5" font-weight="600">AI Extraction Step</text>

            <rect x="220" y="2" width="12" height="12" rx="3" fill="#064E3B" stroke="#10B981" stroke-width="1.5" />
            <text x="238" y="12" fill="#E2E8F0" font-size="10.5" font-weight="600">Deterministic / Parser Step</text>

            <rect x="470" y="2" width="12" height="12" rx="3" fill="#451A03" stroke="#F59E0B" stroke-width="1.5" />
            <text x="488" y="12" fill="#E2E8F0" font-size="10.5" font-weight="600">Decision Gate</text>

            <rect x="680" y="2" width="12" height="12" rx="3" fill="#0F172A" stroke="#38BDF8" stroke-width="1.5" />
            <text x="698" y="12" fill="#E2E8F0" font-size="10.5" font-weight="600">Bounded Feedback Loop</text>
          </g>

          <!-- ==================================================================== -->
          <!-- SUBGRAPH 1: INTAKE & PREPROCESSING                                  -->
          <!-- ==================================================================== -->
          <rect x="40" y="44" width="980" height="174" rx="12" fill="#0B132B" fill-opacity="0.6" stroke="#334155" stroke-dasharray="4 4" stroke-width="1" />
          <text x="56" y="63" fill="#94A3B8" font-size="10" font-weight="700" letter-spacing="1">SUBGRAPH: INGESTION &amp; PREPROCESSING</text>

          <!-- Node: Source Upload -->
          <rect x="55" y="98" width="135" height="66" rx="26" fill="#1E293B" stroke="#64748B" stroke-width="1.5" />
          <text x="122" y="124" fill="#F8FAFC" font-size="11.5" font-weight="700" text-anchor="middle">Source Upload</text>
          <text x="122" y="139" fill="#94A3B8" font-size="9" text-anchor="middle">PDF, Email, JSON, Scans</text>

          <!-- Branch 1 (Top): Native PDF & JSON (BYPASSES PII) -->
          <path d="M 190 131 C 215 131, 222 74, 245 74" stroke="#10B981" stroke-width="1.5" marker-end="url(#m-green)" fill="none" />
          <rect x="198" y="66" width="46" height="14" rx="3" fill="#064E3B" />
          <text x="221" y="76" fill="#A7F3D0" font-size="7.5" font-weight="700" text-anchor="middle">PDF / JSON</text>
          <rect x="248" y="56" width="180" height="38" rx="8" fill="#064E3B" stroke="#10B981" stroke-width="1.5" />
          <text x="338" y="72" fill="#ECFDF5" font-size="10.5" font-weight="700" text-anchor="middle">PDF &amp; JSON Parsers</text>
          <text x="338" y="85" fill="#A7F3D0" font-size="8.5" text-anchor="middle">Native tables &amp; JSONPath</text>

          <!-- Straight connector from PDF/JSON to Prepared Workspace (BYPASSES PII) -->
          <path d="M 428 74 L 758 74" stroke="#10B981" stroke-width="1.5" marker-end="url(#m-green)" />
          <rect x="535" y="66" width="128" height="16" rx="4" fill="#064E3B" stroke="#10B981" stroke-width="1" />
          <text x="599" y="78" fill="#A7F3D0" font-size="8" font-weight="700" text-anchor="middle">Direct (Bypasses PII)</text>

          <!-- Branch 2 (Middle): Email Intake -> Contact PII Redaction -->
          <path d="M 190 131 C 215 131, 225 120, 245 120" stroke="#10B981" stroke-width="1.5" marker-end="url(#m-green)" fill="none" />
          <rect x="202" y="112" width="38" height="14" rx="3" fill="#064E3B" />
          <text x="221" y="122" fill="#A7F3D0" font-size="7.5" font-weight="700" text-anchor="middle">Email</text>
          <rect x="248" y="102" width="180" height="36" rx="8" fill="#064E3B" stroke="#10B981" stroke-width="1.5" />
          <text x="338" y="117" fill="#ECFDF5" font-size="10.5" font-weight="700" text-anchor="middle">Email MIME Parser</text>
          <text x="338" y="130" fill="#A7F3D0" font-size="8.5" text-anchor="middle">MIME headers &amp; body text</text>

          <!-- Connector -> PII Redaction (Emails only) -->
          <path d="M 428 120 L 498 120" stroke="#10B981" stroke-width="1.5" marker-end="url(#m-green)" />

          <!-- Node: Contact PII Redaction -->
          <rect x="500" y="100" width="175" height="40" rx="8" fill="#064E3B" stroke="#10B981" stroke-width="1.5" />
          <text x="587" y="116" fill="#ECFDF5" font-size="10.5" font-weight="700" text-anchor="middle">Contact PII Redaction</text>
          <text x="587" y="129" fill="#A7F3D0" font-size="8.5" text-anchor="middle">Masks greetings &amp; emails</text>

          <!-- Connector from PII Redaction -> Prepared Workspace -->
          <path d="M 675 120 L 758 120" stroke="#10B981" stroke-width="1.5" marker-end="url(#m-green)" />

          <!-- Branch 3 (Bottom): Scanned Images -> OCR Reader & Parser / Direct Vision -->
          <path d="M 190 131 C 215 131, 222 176, 245 176" stroke="#10B981" stroke-width="1.5" fill="none" />
          <rect x="202" y="168" width="38" height="14" rx="3" fill="#064E3B" />
          <text x="221" y="178" fill="#A7F3D0" font-size="7.5" font-weight="700" text-anchor="middle">Scans</text>
          <rect x="248" y="148" width="180" height="34" rx="7" fill="#064E3B" stroke="#10B981" stroke-width="1.5" />
          <text x="338" y="162" fill="#ECFDF5" font-size="10" font-weight="700" text-anchor="middle">OCR Reader &amp; Parser</text>
          <text x="338" y="174" fill="#A7F3D0" font-size="8" text-anchor="middle">Reads &amp; parses text &amp; layout</text>

          <rect x="248" y="186" width="180" height="28" rx="6" fill="#2E1065" stroke="#A78BFA" stroke-width="1.5" />
          <text x="338" y="199" fill="#EDE9FE" font-size="9.5" font-weight="700" text-anchor="middle">Direct Vision</text>
          <text x="338" y="209" fill="#C4B5FD" font-size="7.5" text-anchor="middle">Raw image media</text>

          <!-- Connectors from OCR / Vision -> Prepared Workspace -->
          <path d="M 428 165 L 758 165" stroke="#10B981" stroke-width="1.5" marker-end="url(#m-green)" />
          <path d="M 428 200 C 600 200, 680 165, 758 165" stroke="#A78BFA" stroke-width="1.5" marker-end="url(#m-purple)" />

          <!-- Node: Prepared Evidence Workspace (Right Container) -->
          <rect x="760" y="56" width="185" height="158" rx="10" fill="#1E1B4B" stroke="#818CF8" stroke-width="1.5" />
          <rect x="795" y="68" width="115" height="16" rx="4" fill="#2E1065" stroke="#A78BFA" stroke-width="1" />
          <text x="852" y="79" fill="#DDD6FE" font-size="8" font-weight="700" text-anchor="middle">MEMORY WORKSPACE</text>
          <text x="852" y="104" fill="#F5F3FF" font-size="12" font-weight="700" text-anchor="middle">Prepared Workspace</text>
          <text x="852" y="118" fill="#C7D2FE" font-size="8.5" text-anchor="middle">Multi-format reference context</text>
          <text x="852" y="142" fill="#818CF8" font-size="8" font-weight="600" text-anchor="middle">&bull; PDF &amp; JSON native layout</text>
          <text x="852" y="157" fill="#818CF8" font-size="8" font-weight="600" text-anchor="middle">&bull; Redacted email body text</text>
          <text x="852" y="172" fill="#818CF8" font-size="8" font-weight="600" text-anchor="middle">&bull; Verified OCR text &amp; images</text>

          <!-- Inter-Row 1 -> 2 Routing Path -->
          <path d="M 852 214 L 852 226 Q 852 234 840 234 L 135 234 Q 135 234 135 242 L 135 252" stroke="#818CF8" stroke-width="1.5" stroke-dasharray="4 3" marker-end="url(#m-purple)" fill="none" />
          <rect x="460" y="226" width="140" height="16" rx="4" fill="#1E293B" stroke="#475569" stroke-width="1" />
          <text x="530" y="238" fill="#C7D2FE" font-size="8.5" font-weight="600" text-anchor="middle">Prepared Reference Context</text>

          <!-- ==================================================================== -->
          <!-- SUBGRAPH 2: SEMANTIC EXTRACTION & GROUNDING LOOP                     -->
          <!-- ==================================================================== -->
          <rect x="40" y="222" width="980" height="186" rx="12" fill="#0B132B" fill-opacity="0.6" stroke="#334155" stroke-dasharray="4 4" stroke-width="1" />
          <text x="56" y="243" fill="#94A3B8" font-size="10" font-weight="700" letter-spacing="1">SUBGRAPH: SEMANTIC EXTRACTION &amp; GROUNDING LOOP</text>

          <!-- Node: Primary Extraction -->
          <rect x="55" y="254" width="160" height="52" rx="8" fill="#2E1065" stroke="#A78BFA" stroke-width="1.5" />
          <text x="135" y="276" fill="#F5F3FF" font-size="11.5" font-weight="700" text-anchor="middle">Primary Extraction</text>
          <text x="135" y="291" fill="#DDD6FE" font-size="9" text-anchor="middle">Extract canonical fields</text>

          <!-- Connector -> Valid? Diamond -->
          <path d="M 215 280 L 243 280" stroke="#A78BFA" stroke-width="1.5" marker-end="url(#m-purple)" />

          <!-- Diamond: Valid Schema? -->
          <polygon points="275,255 305,280 275,305 245,280" fill="#451A03" stroke="#F59E0B" stroke-width="1.5" />
          <text x="275" y="283" fill="#FEF3C7" font-size="9" font-weight="700" text-anchor="middle">Valid?</text>

          <!-- Branch: Failed State -->
          <path d="M 275 305 L 275 348" stroke="#F43F5E" stroke-width="1.5" marker-end="url(#m-rose)" />
          <rect x="250" y="318" width="50" height="14" rx="3" fill="#881337" />
          <text x="275" y="328" fill="#FDA4AF" font-size="8" font-weight="600" text-anchor="middle">0 Items</text>
          <rect x="225" y="350" width="100" height="34" rx="6" fill="#881337" stroke="#F43F5E" stroke-width="1" />
          <text x="275" y="371" fill="#FFE4E6" font-size="10" font-weight="700" text-anchor="middle">Failed State</text>

          <!-- Branch: Valid -> Grounding Extraction -->
          <path d="M 305 280 L 343 280" stroke="#F59E0B" stroke-width="1.5" marker-end="url(#m-amber)" />
          <rect x="312" y="272" width="22" height="14" rx="3" fill="#451A03" />
          <text x="323" y="282" fill="#FDE68A" font-size="8" font-weight="700" text-anchor="middle">Yes</text>

          <!-- Node: Grounding Extraction -->
          <rect x="345" y="254" width="165" height="52" rx="8" fill="#2E1065" stroke="#A78BFA" stroke-width="1.5" />
          <text x="427" y="276" fill="#F5F3FF" font-size="11.5" font-weight="700" text-anchor="middle">Grounding Extraction</text>
          <text x="427" y="291" fill="#DDD6FE" font-size="9" text-anchor="middle">Locate exact source text</text>

          <!-- Connector -> Claim Verifier -->
          <path d="M 510 280 L 543 280" stroke="#A78BFA" stroke-width="1.5" marker-end="url(#m-purple)" />

          <!-- Node: Claim Verifier -->
          <rect x="545" y="254" width="160" height="52" rx="8" fill="#064E3B" stroke="#10B981" stroke-width="1.5" />
          <text x="625" y="276" fill="#ECFDF5" font-size="11.5" font-weight="700" text-anchor="middle">Claim Verifier</text>
          <text x="625" y="291" fill="#A7F3D0" font-size="9" text-anchor="middle">Deterministic text check</text>

          <!-- Connector -> Grounded? Diamond -->
          <path d="M 705 280 L 738 280" stroke="#10B981" stroke-width="1.5" marker-end="url(#m-green)" />

          <!-- Diamond: All Grounded? -->
          <polygon points="770,255 802,280 770,305 738,280" fill="#451A03" stroke="#F59E0B" stroke-width="1.5" />
          <text x="770" y="283" fill="#FEF3C7" font-size="8.5" font-weight="700" text-anchor="middle">Grounded?</text>

          <!-- Loop Branch: No (< 3) -->
          <path d="M 770 305 L 770 348" stroke="#38BDF8" stroke-width="1.5" marker-end="url(#m-sky)" />
          <rect x="745" y="318" width="50" height="14" rx="3" fill="#0C2340" />
          <text x="770" y="328" fill="#93C5FD" font-size="8" font-weight="600" text-anchor="middle">No (&lt; 3)</text>

          <!-- Node: Targeted Retry -->
          <rect x="685" y="350" width="170" height="38" rx="8" fill="#0C2340" stroke="#38BDF8" stroke-width="1.5" />
          <text x="770" y="367" fill="#E0F2FE" font-size="10.5" font-weight="700" text-anchor="middle">Targeted Retry</text>
          <text x="770" y="380" fill="#93C5FD" font-size="8.5" text-anchor="middle">Resolve ungrounded fields</text>

          <!-- Loop Back Arrow from Targeted Retry to Grounding Extraction -->
          <path d="M 685 369 C 530 369, 427 335, 427 311" stroke="#38BDF8" stroke-width="1.5" stroke-dasharray="4 3" marker-end="url(#m-sky)" fill="none" />
          <rect x="480" y="362" width="115" height="14" rx="3" fill="#1E293B" />
          <text x="537" y="372" fill="#38BDF8" font-size="8" font-weight="600" text-anchor="middle">&larr; Re-investigate ungrounded</text>

          <!-- Exit Branch: Yes -> Verified Quotation -->
          <path d="M 802 280 L 848 280" stroke="#10B981" stroke-width="1.5" marker-end="url(#m-green)" />
          <rect x="815" y="272" width="22" height="14" rx="3" fill="#064E3B" />
          <text x="826" y="282" fill="#86EFAC" font-size="8" font-weight="700" text-anchor="middle">Yes</text>

          <!-- Node: Verified Quotation -->
          <rect x="850" y="254" width="155" height="52" rx="8" fill="#1E1B4B" stroke="#818CF8" stroke-width="1.5" />
          <text x="927" y="276" fill="#F5F3FF" font-size="11.5" font-weight="700" text-anchor="middle">Verified Quotation</text>
          <text x="927" y="291" fill="#C7D2FE" font-size="9" text-anchor="middle">Canonical data + evidence</text>

          <!-- Inter-Row 2 -> 3 Routing Path -->
          <path d="M 927 306 L 927 416 Q 927 426 915 426 L 142 426 Q 130 426 130 436 L 130 458" stroke="#10B981" stroke-width="1.5" stroke-dasharray="4 3" marker-end="url(#m-green)" fill="none" />
          <rect x="460" y="418" width="140" height="16" rx="4" fill="#1E293B" stroke="#475569" stroke-width="1" />
          <text x="530" y="430" fill="#86EFAC" font-size="8.5" font-weight="600" text-anchor="middle">Validated Line Items &amp; Evidence</text>

          <!-- ==================================================================== -->
          <!-- SUBGRAPH 3: NORMALIZATION & REVIEW ROUTING                           -->
          <!-- ==================================================================== -->
          <rect x="40" y="442" width="980" height="186" rx="12" fill="#0B132B" fill-opacity="0.6" stroke="#334155" stroke-dasharray="4 4" stroke-width="1" />
          <text x="56" y="463" fill="#94A3B8" font-size="10" font-weight="700" letter-spacing="1">SUBGRAPH: NORMALIZATION, CONFIDENCE &amp; ROUTING</text>

          <!-- Node: Commercial Normalization -->
          <rect x="55" y="474" width="175" height="52" rx="8" fill="#064E3B" stroke="#10B981" stroke-width="1.5" />
          <text x="142" y="496" fill="#ECFDF5" font-size="11.5" font-weight="700" text-anchor="middle">Commercial Math</text>
          <text x="142" y="511" fill="#A7F3D0" font-size="9" text-anchor="middle">Pack price &amp; unit normalization</text>

          <!-- Connector -> Confidence Engine -->
          <path d="M 230 500 L 298 500" stroke="#10B981" stroke-width="1.5" marker-end="url(#m-green)" />
          <rect x="238" y="492" width="50" height="16" rx="4" fill="#065F46" />
          <text x="263" y="503" fill="#A7F3D0" font-size="8.5" font-weight="700" text-anchor="middle">+5% Bonus</text>

          <!-- Node: Confidence Engine -->
          <rect x="300" y="474" width="185" height="52" rx="8" fill="#1E293B" stroke="#64748B" stroke-width="1.5" />
          <text x="392" y="496" fill="#F8FAFC" font-size="11.5" font-weight="700" text-anchor="middle">Confidence Engine</text>
          <text x="392" y="511" fill="#94A3B8" font-size="9" text-anchor="middle">Quality score &amp; 5-tier mapping</text>

          <!-- Connector -> Quality Gate Diamond -->
          <path d="M 485 500 L 523 500" stroke="#64748B" stroke-width="1.5" marker-end="url(#m-slate)" />

          <!-- Diamond: Quality Gate -->
          <polygon points="555,475 588,500 555,525 522,500" fill="#1E293B" stroke="#94A3B8" stroke-width="1.5" />
          <text x="555" y="503" fill="#F1F5F9" font-size="8.5" font-weight="700" text-anchor="middle">Quality Gate</text>

          <!-- 3 Branches from Diamond -->
          <!-- Branch 1: Pre-Approved -->
          <path d="M 588 500 C 618 500, 628 468, 668 468" stroke="#10B981" stroke-width="1.5" marker-end="url(#m-green)" fill="none" />
          <rect x="595" y="460" width="65" height="14" rx="3" fill="#064E3B" />
          <text x="627" y="470" fill="#86EFAC" font-size="7.5" font-weight="700" text-anchor="middle">100% &amp; 0 Issues</text>
          <rect x="670" y="450" width="220" height="38" rx="19" fill="#064E3B" stroke="#10B981" stroke-width="1.5" />
          <text x="780" y="466" fill="#ECFDF5" font-size="11" font-weight="700" text-anchor="middle">🟢 Pre-Approved</text>
          <text x="780" y="479" fill="#A7F3D0" font-size="8.5" text-anchor="middle">Instant pass &bull; Zero human touch</text>

          <!-- Branch 2: Needs Review -->
          <path d="M 588 500 L 668 500" stroke="#F59E0B" stroke-width="1.5" marker-end="url(#m-amber)" />
          <rect x="595" y="493" width="65" height="14" rx="3" fill="#78350F" />
          <text x="627" y="503" fill="#FDE68A" font-size="7.5" font-weight="700" text-anchor="middle">70–99% / Issues</text>
          <rect x="670" y="482" width="220" height="38" rx="19" fill="#78350F" stroke="#F59E0B" stroke-width="1.5" />
          <text x="780" y="498" fill="#FEFCE8" font-size="11" font-weight="700" text-anchor="middle">🟡 Needs Review</text>
          <text x="780" y="511" fill="#FDE68A" font-size="8.5" text-anchor="middle">Routed to review desk for audit</text>

          <!-- Branch 3: Material Unusable -->
          <path d="M 588 500 C 618 500, 628 534, 668 534" stroke="#F43F5E" stroke-width="1.5" marker-end="url(#m-rose)" fill="none" />
          <rect x="595" y="527" width="65" height="14" rx="3" fill="#881337" />
          <text x="627" y="537" fill="#FDA4AF" font-size="7.5" font-weight="700" text-anchor="middle">Image &lt; 50%</text>
          <rect x="670" y="516" width="220" height="38" rx="19" fill="#881337" stroke="#F43F5E" stroke-width="1.5" />
          <text x="780" y="532" fill="#FFF1F2" font-size="11" font-weight="700" text-anchor="middle">🔴 Material Unusable</text>
          <text x="780" y="545" fill="#FECDD3" font-size="8.5" text-anchor="middle">Non-approvable lock &bull; Audit trail</text>
        </svg>
      </div>
    </div>
  </div>
</template>

