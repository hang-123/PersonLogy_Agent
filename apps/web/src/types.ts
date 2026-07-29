export type ApiState = "checking" | "online" | "offline";

export type CandidateKind = "object" | "attribute" | "relation" | "claim" | "evidence";
export type CandidateStatus = "pending_review" | "accepted" | "rejected" | "merged";
export type ObjectType =
  | "company"
  | "department"
  | "position"
  | "jd_version"
  | "skill"
  | "experience";

export interface HealthResponse {
  status: "ok";
  service: string;
  version: string;
}

export interface Evidence {
  id: string;
  source_document_id: string;
  excerpt: string;
  locator: Record<string, unknown>;
  content_fingerprint: string;
  source_level: string | null;
  status: "active" | "locator_invalid" | "archived";
  visibility: "public" | "private" | "sensitive";
  captured_at: string;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface SourceDocument {
  id: string;
  title: string;
  source_type: "text" | "web" | "pdf" | "markdown" | "image" | "other";
  source_url: string | null;
  storage_path: string | null;
  raw_text: string | null;
  content_fingerprint: string;
  content_size: number;
  status: string;
  visibility: "public" | "private" | "sensitive";
  source_metadata: Record<string, unknown>;
  captured_at: string;
  version: number;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface SourceDetail extends SourceDocument {
  evidence: Evidence[];
}

export interface SourceList {
  items: SourceDocument[];
  total: number;
  limit: number;
  offset: number;
}

export interface Candidate {
  id: string;
  candidate_kind: CandidateKind;
  status: CandidateStatus;
  payload: Record<string, unknown>;
  source_document_id: string | null;
  created_by: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  rejection_reason: string | null;
  published_target_kind: string | null;
  published_target_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface CandidateList {
  items: Candidate[];
  total: number;
  limit: number;
  offset: number;
}

export interface KnowledgeObject {
  id: string;
  object_type: ObjectType;
  canonical_name: string;
  display_name: string;
  status: string;
  aliases: string[];
  attributes: Record<string, unknown>;
  visibility: string;
  version: number;
  created_by: string;
  reviewed_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeObjectList {
  items: KnowledgeObject[];
  total: number;
  limit: number;
  offset: number;
}

export interface PublishResult {
  candidate_id: string;
  candidate_status: CandidateStatus;
  target_kind: string;
  target_id: string;
  target_version: number;
}

export interface ApiErrorPayload {
  error?: {
    code?: string;
    message?: string;
  };
  detail?: string | Array<{ msg?: string }>;
}
