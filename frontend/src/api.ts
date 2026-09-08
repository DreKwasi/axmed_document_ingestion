/** REST API client for Axmed Document Intelligence backend. */

import type { DocumentResponse, ProcessingEvent } from "@/types";

// --- Section 1: Configuration & HTTP Transport ---

const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL || "").replace(/\/+$/, "") ||
  "http://127.0.0.1:8000";

class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(body.detail ?? "The request could not be completed.", response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

// --- Section 2: Ingestion & Document Operations ---

/** Uploads quotation files for background processing. */
export function uploadDocuments(files: File[]): Promise<DocumentResponse[]> {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  return request("/api/v1/documents", { method: "POST", body: formData });
}

/** Retrieves all ingested documents. */
export function fetchDocuments(): Promise<DocumentResponse[]> {
  return request("/api/v1/documents");
}

/** Retrieves a single document by UUID. */
export function fetchDocument(documentId: string): Promise<DocumentResponse> {
  return request(`/api/v1/documents/${documentId}`);
}

/** Permanently deletes a document and associated data. */
export function deleteDocument(documentId: string): Promise<void> {
  return request(`/api/v1/documents/${documentId}`, { method: "DELETE" });
}

// --- Section 3: Extraction Pipelines & Peer Reviews ---

/** Re-triggers extraction for a document. */
export function reextractDocument(documentId: string): Promise<DocumentResponse> {
  return request(`/api/v1/documents/${documentId}/reextract`, { method: "POST" });
}

/** Promotes a specific image extraction approach (ocr_assisted vs vision_direct) for review. */
export function openImageExtractionForReview(
  documentId: string,
  approach: string
): Promise<DocumentResponse> {
  return request(`/api/v1/documents/${documentId}/image-extractions/${approach}/review`, {
    method: "POST"
  });
}

// --- Section 4: Real-Time Streaming & Asset URLs ---

/** Direct URL to download or view raw uploaded source file. */
export function sourceDocumentUrl(documentId: string): string {
  return `${API_BASE_URL}/api/v1/documents/${documentId}/source`;
}

/** Server-Sent Events URL for live progress streaming. */
export function eventStreamUrl(documentId: string, afterId = 0): string {
  return `${API_BASE_URL}/api/v1/documents/${documentId}/events/stream?after_id=${afterId}`;
}

/** Fetches recent activity events for a document. */
export function fetchEvents(documentId: string, afterId = 0): Promise<ProcessingEvent[]> {
  return request(`/api/v1/documents/${documentId}/events?after_id=${afterId}`);
}

// --- Section 5: Human Review Decisions ---

/** Submits human approval, rejection, or field correction decisions. */
export function reviewDocument(
  documentId: string,
  action: "approve" | "reject" | "correct",
  command: {
    request_id: string;
    expected_revision: number;
    note?: string;
    rejection_reason?: string;
    patches?: Array<{ path: string; value: unknown }>;
  }
): Promise<DocumentResponse> {
  return request(`/api/v1/documents/${documentId}/reviews/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(command)
  });
}


