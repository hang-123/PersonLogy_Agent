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

export interface ContentBlock {
  id: string;
  source_version_id: string;
  ordinal: number;
  content: string;
  content_hash: string;
  locator: Record<string, unknown>;
}

export interface SourceVersionDetail {
  id: string;
  source_id: string;
  version: number;
  content_hash: string;
  created_at: string;
  content_available: boolean;
  blocks: ContentBlock[];
}

export interface EvidenceDetail {
  id: string;
  quote: string;
  locator: Record<string, unknown>;
  metadata: Record<string, unknown>;
  content_block: ContentBlock;
  source_version: Omit<SourceVersionDetail, "blocks">;
}

export interface RetrievalAnswerResponse {
  project_id: string;
  question: string;
  answer: string;
  mode: string;
  hit_count: number;
  hits: RetrievalHit[];
  citations: Citation[];
  relations: RelationPath[];
  uncertainty: string[];
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

export interface HealthResponse {
  status: "ok";
  service: string;
  version: string;
}

export interface ApiErrorPayload {
  error?: {
    code?: string;
    message?: string;
  };
  detail?: string | Array<{ msg?: string }>;
}
