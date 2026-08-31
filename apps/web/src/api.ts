import type {
  ApiErrorPayload,
  HealthResponse,
} from "./types";
import type {
  ConversationImportRequest,
  ConversationImportResponse,
  Job,
  LineageTrace,
  PdfImportResponse,
  EvidenceDetail,
  RetrievalSearchResponse,
  RetrievalAnswerResponse,
  ReviewTask,
  SourceVersionDetail,
} from "./types";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/v1";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (!(init?.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(apiBaseUrl + path, {
    ...init,
    headers,
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as ApiErrorPayload;
    const detail = Array.isArray(payload.detail)
      ? payload.detail.map((item) => item.msg).filter(Boolean).join("; ")
      : payload.detail;
    throw new ApiError(
      payload.error?.message ?? detail ?? "请求失败（HTTP " + response.status + "）",
      response.status,
      payload.error?.code ?? "http_error",
    );
  }
  return (await response.json()) as T;
}

function queryString(values: Record<string, string | number | boolean | undefined>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined && value !== "") {
      params.set(key, String(value));
    }
  }
  const encoded = params.toString();
  return encoded ? "?" + encoded : "";
}

export const api = {
  health: () => request<HealthResponse>("/health/live"),

  uploadPdf: (payload: {
    projectName: string;
    projectSlug: string;
    title: string;
    file: File;
  }) => {
    const formData = new FormData();
    formData.set("project_name", payload.projectName);
    formData.set("project_slug", payload.projectSlug);
    formData.set("title", payload.title);
    formData.set("file", payload.file);
    return request<PdfImportResponse>("/pdfs/upload", {
      method: "POST",
      body: formData,
    });
  },

  importConversation: (payload: ConversationImportRequest) =>
    request<ConversationImportResponse>("/conversations/import", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  listJobs: (limit = 100) => request<Job[]>("/jobs?limit=" + limit),

  getJob: (jobId: string) => request<Job>("/jobs/" + encodeURIComponent(jobId)),

  listReviewTasks: (limit = 100) => request<ReviewTask[]>("/review-tasks?limit=" + limit),

  getReviewTask: (taskId: string) =>
    request<ReviewTask>("/review-tasks/" + encodeURIComponent(taskId)),

  decideReviewTask: (
    taskId: string,
    payload: {
      decision: "approved" | "rejected" | "revised";
      reviewer_id: string;
      reason: string;
      expected_version?: number;
      changes?: Record<string, unknown>;
    },
  ) =>
    request<ReviewTask>("/review-tasks/" + encodeURIComponent(taskId) + "/decision", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  searchRetrieval: (payload: { projectId: string; query: string; limit?: number; expandRelations?: boolean }) =>
    request<RetrievalSearchResponse>(
      "/retrieval/search" +
        queryString({
          project_id: payload.projectId,
          q: payload.query,
          limit: payload.limit ?? 20,
          expand_relations: payload.expandRelations ?? false,
        }),
    ),

  answerRetrieval: (payload: { projectId: string; question: string; limit?: number; expandRelations?: boolean }) =>
    request<RetrievalAnswerResponse>("/retrieval/answer", {
      method: "POST",
      body: JSON.stringify({
        project_id: payload.projectId,
        question: payload.question,
        limit: payload.limit ?? 5,
        expand_relations: payload.expandRelations ?? false,
      }),
    }),

  getSourceVersion: (sourceVersionId: string, projectId: string) =>
    request<SourceVersionDetail>(
      "/source-versions/" + encodeURIComponent(sourceVersionId) + queryString({ project_id: projectId }),
    ),

  getEvidence: (evidenceId: string, projectId: string) =>
    request<EvidenceDetail>(
      "/evidence/" + encodeURIComponent(evidenceId) + queryString({ project_id: projectId }),
    ),

  sourceVersionContentUrl: (sourceVersionId: string, projectId: string) =>
    apiBaseUrl + "/source-versions/" + encodeURIComponent(sourceVersionId) + "/content" + queryString({ project_id: projectId }),

  traceClaim: (payload: { projectId: string; claimId: string; limit?: number }) =>
    request<LineageTrace>(
      "/lineage/claims/" +
        encodeURIComponent(payload.claimId) +
        queryString({ project_id: payload.projectId, limit: payload.limit ?? 1000 }),
    ),

};
