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
  published_at?: string;
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
  accepted: boolean;
  reason?: string;
  claims?: EvidenceClaim[];
}

export interface RunManifest {
  run_id: string;
  schema_version: 3;
  started_at: string;
  completed_at?: string;
  document_ids: string[];
  candidate_ids: string[];
  decision_ids: string[];
}
