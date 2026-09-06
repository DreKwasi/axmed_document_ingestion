import type { DocumentResponse, EvaluationsResponse } from "@/types";

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
  return response.json() as Promise<T>;
}

export function uploadDocument(file: File): Promise<DocumentResponse> {
  const formData = new FormData();
  formData.append("file", file);
  return request("/api/v1/documents", { method: "POST", body: formData });
}

export function confirmMapping(documentId: string): Promise<DocumentResponse> {
  return request(`/api/v1/documents/${documentId}/mapping/confirm`, { method: "POST" });
}

export function fetchEvaluations(): Promise<EvaluationsResponse> {
  return request("/api/v1/evaluations");
}

export function runEvaluation(): Promise<{ id: string; status: string }> {
  return request("/api/v1/evaluations/runs", { method: "POST" });
}
