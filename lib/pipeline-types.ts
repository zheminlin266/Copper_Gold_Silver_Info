export type PipelineKind = "broadcast" | "x" | "news";
export type PipelineDecision = "accept" | "accepted" | "reject" | "rejected";
export type CollectorStatus = "preflight" | "complete" | "partial" | "failed";

export interface RawDocument {
  id: string;
  source_url: string;
  title: string;
  text: string;
  published_at?: string;
}

export interface Candidate {
  id: string;
  document_id: string;
  source_url: string;
  title: string;
  text: string;
  published_at?: string;
  collector: string;
  kind?: PipelineKind;
  source?: string;
  author?: string;
  handle?: string;
  metal?: "gold" | "silver" | "copper";
  direction?: "supply" | "demand" | "both";
  raw?: Record<string, unknown>;
}

export interface EvidenceClaim {
  claim: string;
  evidence: string;
  source_url: string;
  evidence_type: string;
  period: string;
  unit: string;
  value: string | number | null;
}

export interface AnalysisDecision {
  candidate_id: string;
  accepted?: boolean;
  decision?: PipelineDecision;
  reason?: string;
  kind?: PipelineKind;
  metal?: "gold" | "silver" | "copper";
  direction?: "supply" | "demand" | "both";
  confidence?: number;
  claims?: EvidenceClaim[];
}

export interface CollectorResult {
  collector: string;
  status: CollectorStatus;
  candidates: Candidate[];
  errors: string[];
  exit_code: number | null;
  stdout: string;
  stderr: string;
  artifacts: string[];
}

export interface RunManifest {
  run_id: string;
  schema_version: 3;
  started_at: string;
  completed_at?: string;
  report_date?: string;
  run_dir?: string;
  windows: Record<string, { start: string; end: string }>;
  status: CollectorStatus;
  document_ids: string[];
  candidate_ids: string[];
  decision_ids: string[];
  collectors: Array<Record<string, unknown>>;
  registry_source_ids: string[];
}
