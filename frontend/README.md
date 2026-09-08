# Axmed Review Desk — Frontend

Single-page web application built with **Vue 3**, **TypeScript**, **Tailwind CSS**, and **Vite** for the Axmed Supplier Document Intelligence platform. Provides a Home source list, source-level review, product breakdown, batch file uploader, and live Server-Sent Events (SSE) processing updates.

- 🌐 **Live Platform (Cloudflare Pages)**: [https://axmed-document-ingestion.pages.dev/](https://axmed-document-ingestion.pages.dev/)
- 🚀 **Connected Live Backend API**: [https://axmeddocumentingestion-production.up.railway.app](https://axmeddocumentingestion-production.up.railway.app)

---

## Prerequisites

- **Node.js 22+**
- **npm** (or pnpm / yarn)

---

## Quick Setup & Installation

From within the `frontend/` directory (or using `--prefix frontend` from repository root):

```bash
# Install dependencies
npm install

# Optional: configure API URL if backend is running on a non-standard port
cp .env.example .env
```

---

## Configuration

The frontend connects to the FastAPI backend API. By default, it targets `http://127.0.0.1:8000`. You can override this in `frontend/.env`:

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000` | Base URL of the running FastAPI backend |

---

## Running the Application

### Development Server
Starts Vite development server with Hot Module Replacement (HMR):

```bash
npm run dev
```
- Open your browser at: **[http://127.0.0.1:5173](http://127.0.0.1:5173)**

*(Note: If you want to start both the FastAPI backend and Vue frontend together, run `make dev` from the repository root).*

### Production Build & Type-Checking
Type-checks the TypeScript code with `vue-tsc` and bundles optimized production assets into `dist/`:

```bash
npm run build
```

---

## Testing & Code Quality

### 1. Unit & Component Tests (Vitest)
Runs fast component tests (using `@vue/test-utils` and `jsdom`):

```bash
npm test
```

### 2. Code Linting (ESLint)
Checks Vue templates, TypeScript, and styling against strict rules:

```bash
npm run lint
```

### 3. Browser End-to-End Tests (Playwright)
Executes end-to-end user journeys against a real browser. Playwright automatically starts an isolated backend and frontend test server on port 15173:

```bash
# Run headless browser tests
npm run test:e2e

# Run with interactive visual Playwright UI
npx playwright test --ui
```

---

## Feature Tour

### 1. Multi-Document & Folder Batch Ingestion
- Upload single files or drag-and-drop entire folders (`.json`, `.pdf`, `.eml`, `.png`, `.jpg`).
- Tracks aggregate batch ingestion progress in real-time.
- **Failure Isolation**: Corrupt or unsupported files in a batch fail safely with isolated badges without blocking valid sibling documents.

### 2. Real-Time Reconnectable SSE Timeline
- Connects to `/api/v1/documents/{id}/events` via Server-Sent Events.
- Displays stage-by-stage pipeline progress: `received` → `pii_redacted` → `semantic_extraction` → `commercially_validated`.
- Supports durable reconnection using the standard `Last-Event-ID` header.

### 3. Review Desk & Commercial Intelligence
- **Preserved Basis & Derived Prices**: Shows original supplier pricing (e.g. `EUR 3.15 / pack`) alongside derived unit prices (`EUR 0.035 / tablet`) calculated by deterministic business rules.
- **Commercial Validation Warnings**: Flags minimum order quantity (MOQ) violations, expired offers, and non-standard packaging terms.
- **Field-Level Provenance**: Hover or click any field to inspect the exact source text, page bounds, and extraction method (e.g. `deterministic_mapping`, `langchain-gemini`).

### 4. Human-in-the-Loop Review Controls
- **Source-grounded JSON extraction**: JSON uploads are interpreted independently. Correctly recovered facts are retained even when they do not yet have a certain canonical destination.
- **Inline Field Corrections**: Correct any misread canonical field and retain an immutable revision trail.
- **Decision Boundary**: Explicitly Approve or Reject quotations before export.
- **User-facing CSV**: Export terminal source results as product rows with source context, confidence explanations, mapping issues, and review history; queued and actively processing sources are omitted.

---

## Directory Architecture

```text
frontend/
├── src/
│   ├── api.ts          # Strongly typed fetch client & SSE event source wrappers
│   ├── types.ts        # TypeScript interfaces matching backend CanonicalQuotation
│   ├── App.vue         # Home source list, source detail, product review, and upload UI
│   ├── styles.css      # Tailwind entrypoint
│   ├── main.ts         # Vue 3 application entry point
│   └── App.spec.ts     # Vitest component test suite
├── e2e/                # Playwright End-to-End test specs:
│   ├── review.spec.ts  # End-to-end review, correction, and approval journey
│   └── batch.spec.ts   # Multi-file batch upload and progress tracking journey
├── playwright.config.ts# Playwright E2E configuration & automated webServer launcher
├── vite.config.ts      # Vite bundler, alias, and test configuration
└── package.json        # Frontend dependencies and npm scripts
```
