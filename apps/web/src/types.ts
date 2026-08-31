export type ApiState = "checking" | "online" | "offline";

export type JobStatus = "queued" | "running" | "retrying" | "succeeded" | "failed" | "cancelled";

export interface ProjectContext {
  projectName: string;
  projectSlug: string;
  projectId?: string;
}

export interface PdfImportResponse {
  project_id: string;
  source_id: string;
  source_version_id: string;
  version: number;
  content_hash: string;
  object_key: string;
  page_count: number;
  job_id: string;
  reused_version: boolean;
}

export interface ConversationImportMessage {
  message_id: string;
  role: string;
  content: string;
  ordinal: number;
  created_at?: string | null;
  parent_message_id?: string | null;
  attachments?: Array<Record<string, unknown>>;
}

export interface ConversationImportRequest {
  project_name: string;
  project_slug: string;
  conversation_id: string;
  title: string;
  messages: ConversationImportMessage[];
  metadata?: Record<string, unknown>;
}

export interface ConversationImportResponse {
  project_id: string;
  source_id: string;
  conversation_id: string;
  job_id: string;
  imported_message_count: number;
  duplicate_message_count: number;
}

export interface Job {
  id: string;
  kind: string;
  idempotency_key: string;
  status: JobStatus;
  progress: number;
  stage: string;
  attempt: number;
  max_attempts: number;
  failure_reason: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface ReviewTask {
  id: string;
  run_id: string;
  candidate_id: string;
  candidate_kind: string;
  status: string;
  reviewer_id: string | null;
  reason: string | null;
  version: number;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  created_at: string;
  reviewed_at: string | null;
}

export interface Citation {
  citation_id: string;
  quote: string;
  source_id: string;
  source_title: string;
  source_version_id: string;
  locator: Record<string, unknown>;
}

export interface RelationPath {
  relation_id: string;
  relation_type: string;
  direction: string;
  source_id: string;
  source_title: string;
  target_id: string;
  target_title: string;
}

export interface RetrievalHit {
  claim_id: string;
  project_id: string;
  statement: string;
  subject_id: string;
  subject_title: string;
  score: number;
  evidence: Citation[];
  relations: RelationPath[];
}

export interface RetrievalSearchResponse {
  project_id: string;
  query: string;
  hits: RetrievalHit[];
}

export interface LineageLink {
  link_id: string;
  project_id: string;
  from_type: string;
  from_id: string;
  relation_type: string;
  to_type: string;
  to_id: string;
  created_at: string;
  metadata: Record<string, unknown>;
}

export interface LineageTrace {
  root_type: string;
  root_id: string;
  links: LineageLink[];
}

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
