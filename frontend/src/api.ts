import type { DocumentResponse, ProcessingEvent } from "@/types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
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

export function uploadDocuments(files: File[]): Promise<DocumentResponse[]> {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  return request("/api/v1/documents", { method: "POST", body: formData });
}

export function fetchDocuments(): Promise<DocumentResponse[]> {
  return request("/api/v1/documents");
}

export function deleteDocument(documentId: string): Promise<void> {
  return request(`/api/v1/documents/${documentId}`, { method: "DELETE" });
}

export function reextractDocument(documentId: string): Promise<DocumentResponse> {
  return request(`/api/v1/documents/${documentId}/reextract`, { method: "POST" });
}

export function openImageExtractionForReview(
  documentId: string,
  approach: string
): Promise<DocumentResponse> {
  return request(`/api/v1/documents/${documentId}/image-extractions/${approach}/review`, {
    method: "POST"
  });
}

export function sourceDocumentUrl(documentId: string): string {
  return `${API_BASE_URL}/api/v1/documents/${documentId}/source`;
}

export function eventStreamUrl(documentId: string, afterId = 0): string {
  return `${API_BASE_URL}/api/v1/documents/${documentId}/events/stream?after_id=${afterId}`;
}

export function fetchDocument(documentId: string): Promise<DocumentResponse> {
  return request(`/api/v1/documents/${documentId}`);
}

export function fetchEvents(documentId: string, afterId = 0): Promise<ProcessingEvent[]> {
  return request(`/api/v1/documents/${documentId}/events?after_id=${afterId}`);
}

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
