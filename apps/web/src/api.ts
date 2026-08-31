import type {
  ApiErrorPayload,
  Candidate,
  CandidateKind,
  CandidateList,
  CandidateStatus,
  Evidence,
  HealthResponse,
  KnowledgeObjectList,
  ObjectType,
  PublishResult,
  SourceDetail,
  SourceDocument,
  SourceList,
} from "./types";
import type {
  ConversationImportRequest,
  ConversationImportResponse,
  Job,
  LineageTrace,
  PdfImportResponse,
  RetrievalSearchResponse,
  ReviewTask,
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

  traceClaim: (payload: { projectId: string; claimId: string; limit?: number }) =>
    request<LineageTrace>(
      "/lineage/claims/" +
        encodeURIComponent(payload.claimId) +
        queryString({ project_id: payload.projectId, limit: payload.limit ?? 1000 }),
    ),

  listSources: (query?: string) =>
    request<SourceList>("/sources" + queryString({ query, limit: 50 })),

  getSource: (sourceId: string) => request<SourceDetail>("/sources/" + sourceId),

  createSource: (payload: {
    title: string;
    source_type: string;
    source_url?: string;
    raw_text: string;
    visibility: string;
    created_by: string;
  }) =>
    request<SourceDocument>("/sources", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  createEvidence: (
    sourceId: string,
    payload: {
      excerpt: string;
      locator: Record<string, unknown>;
      source_level?: string;
      visibility: string;
      created_by: string;
    },
  ) =>
    request<Evidence>("/sources/" + sourceId + "/evidence", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  createCandidate: (payload: {
    candidate_kind: CandidateKind;
    payload: Record<string, unknown>;
    source_document_id?: string;
    created_by: string;
  }) =>
    request<Candidate>("/candidates", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  listCandidates: (filters: {
    status?: CandidateStatus;
    candidateKind?: CandidateKind;
  }) =>
    request<CandidateList>(
      "/candidates" +
        queryString({
          status: filters.status,
          candidate_kind: filters.candidateKind,
          limit: 100,
        }),
    ),

  acceptCandidate: (
    candidateId: string,
    payload: { reviewed_by: string; reason: string; changes: Record<string, unknown> },
  ) =>
    request<PublishResult>("/candidates/" + candidateId + "/accept", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  rejectCandidate: (
    candidateId: string,
    payload: { reviewed_by: string; reason: string },
  ) =>
    request<Candidate>("/candidates/" + candidateId + "/reject", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  mergeCandidate: (
    candidateId: string,
    payload: {
      target_object_id: string;
      reviewed_by: string;
      reason: string;
      aliases: string[];
    },
  ) =>
    request<PublishResult>("/candidates/" + candidateId + "/merge", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  searchObjects: (filters: { objectType?: ObjectType; query?: string }) =>
    request<KnowledgeObjectList>(
      "/objects" +
        queryString({
          object_type: filters.objectType,
          query: filters.query,
          limit: 20,
        }),
    ),
};
