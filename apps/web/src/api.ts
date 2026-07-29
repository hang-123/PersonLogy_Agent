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
  const response = await fetch(apiBaseUrl + path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
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
