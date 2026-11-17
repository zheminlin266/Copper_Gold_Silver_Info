import type { EvidenceClaim } from "@/lib/pipeline-types";

export type { EvidenceClaim } from "@/lib/pipeline-types";

export const CURRENT_REPORT_SCHEMA_VERSION = 3 as const;
export type ReportSchemaVersion = typeof CURRENT_REPORT_SCHEMA_VERSION;

export type Metal = "gold" | "silver" | "copper";
export type SupplyDemand = "supply" | "demand" | "both";
export type Part2Channel = "browser_use" | "rss_fallback" | "web_access_xai" | "twscrape" | "playwright" | "grok_x" | "failed";
export type XSourceChannel = Exclude<Part2Channel, "failed">;
export type NewsSourceChannel = "web" | "playwright";
export type VerificationStatus = "verified" | "unverified";

export interface Guest {
  name?: string;
  background?: string;
}

export interface Broadcast {
  title: string;
  url: string;
  publish_date: string;
  source_type: "podcast" | "webcast" | "youtube" | "conference_interview" | "panel" | "keynote" | "company_presentation";
  metal_tags: Metal[];
  primary_metal?: Metal;
  supply_demand: SupplyDemand;
  summary: string;
  detail?: string;
  importance?: string;
  verification_status?: VerificationStatus;
  verification_note?: string;
  guest?: Guest;
  companies?: string[];
  projects?: string[];
  claims?: EvidenceClaim[];
}

export interface XPost {
  author: string;
  handle: string;
  publish_time: string;
  metal_tags: Metal[];
  primary_metal?: Metal;
  supply_demand: SupplyDemand;
  excerpt?: string;
  interpretation?: string;
  importance?: string;
  verification_status?: VerificationStatus;
  verification_note?: string;
  url: string;
  source_channel?: XSourceChannel;
  claims?: EvidenceClaim[];
}

export interface NewsItem {
  source: string;
  title: string;
  url: string;
  publish_time: string;
  metal_tags: Metal[];
  primary_metal?: Metal;
  supply_demand: SupplyDemand;
  excerpt?: string;
  interpretation?: string;
  importance?: string;
  verification_status?: VerificationStatus;
  verification_note?: string;
  language: "en" | "zh";
  duplicate_of?: string | null;
  companies?: string[];
  projects?: string[];
  mining_com_source_note?: string;
  source_channel?: NewsSourceChannel;
  claims?: EvidenceClaim[];
}

export type UrlVerificationFailure = string | { url: string; reason: string };

export interface UrlVerification {
  checked: number;
  passed: number;
  failed: number;
  failures?: UrlVerificationFailure[];
  notes?: string | string[];
}

export interface ImageSource {
  method: "og_image" | "ai_generated";
  og_image_url?: string;
  source_url?: string;
  prompt?: string;
  note?: string;
}

export type HistoricalPart2Channel = "web_access_xai" | "twscrape" | "playwright";
export type CurrentPart2Channel = "grok_x" | "playwright" | "twscrape";
export type Part2SelectedChannel =
  | HistoricalPart2Channel
  | "web_access_xai+twscrape"
  | "web_access_xai+playwright"
  | "twscrape+playwright"
  | "web_access_xai+twscrape+playwright"
  | "playwright+twscrape"
  | "grok_x"
  | "grok_x+playwright"
  | "grok_x+twscrape"
  | "grok_x+playwright+twscrape";

export interface Part2Coverage {
  status: "complete" | "partial" | "failed";
  accounts_total: number;
  accounts_completed: number;
  accounts_failed: number;
  attempted_channels: Array<HistoricalPart2Channel | CurrentPart2Channel>;
  selected_channel: Part2SelectedChannel | null;
  channel_errors: string[];
  notes: string | string[];
}

export interface SearchLog {
  part1_searched: boolean;
  part1_sources_checked?: string[];
  part1_result?: string;
  part2_searched: boolean;
  part2_channel?: Part2Channel;
  part2_sources_checked?: string[];
  part2_result?: string;
  part2_coverage?: Part2Coverage;
  part3_searched?: boolean;
  part3_sources_checked: string[];
  part3_result?: string;
  mining_com_source_note?: string;
  image_source?: ImageSource;
  new_sources_discovered?: string[];
  url_verification?: UrlVerification;
  research_audit?: ResearchAudit;
}

export interface ResearchSourceAudit {
  source_id: string;
  kind: "broadcast" | "news";
  status: "complete" | "partial" | "failed";
  entry_urls: string[];
  termination: "end_of_window" | "end_of_results" | "error";
  note: string;
  discovered_count: number;
  candidate_ids: string[];
}

export interface ResearchXAccount {
  handle: string;
  user_id: string;
  resolved_handle: string;
  identity_verified: boolean;
  pagination_complete: boolean;
  status: "complete" | "partial" | "failed";
  channel: CurrentPart2Channel | null;
  note: string;
  candidate_ids: string[];
}

export interface ResearchAudit {
  version: 1;
  policy_version: number;
  manifest_sha256: string;
  sources: ResearchSourceAudit[];
  candidates: Array<{
    id: string; source_id: string; source_url: string; kind: "broadcast" | "x" | "news";
    title: string; published_at: string | null; content_checked: boolean; handle?: string;
    decision: "accept" | "reject"; reason_code: string; reason: string; signal_url: string | null;
  }>;
  x_registry: Array<{ handle: string; user_id: string }>;
  x_accounts: ResearchXAccount[];
}

export interface DedupLog {
  part1_deduped_urls: string[];
  part2_deduped_urls?: string[];
  part3_deduped_events: string[];
  notes?: string;
}

export interface DailyReport {
  schema_version?: ReportSchemaVersion;
  date: string;
  report_time: string;
  summary: string;
  migration_note?: string;
  report_note?: string;
  windows: {
    part1: { start: string; end: string };
    part2: { start: string; end: string };
    part3: { start: string; end: string };
  };
  part1_broadcasts: Broadcast[];
  part2_x_posts: XPost[];
  part3_news: NewsItem[];
  search_log: SearchLog;
  dedup_log: DedupLog;
}

export interface ReportSignal {
  id: string;
  kind: "Broadcast" | "X" | "News";
  title: string;
  source: string;
  publishedAt: string;
  metalTags: Metal[];
  primaryMetal: Metal;
  direction: SupplyDemand;
  fact: string;
  interpretation: string;
  importance: string;
  verificationStatus: VerificationStatus;
  verificationNote: string;
  url: string;
  language?: "en" | "zh";
}

export interface ReportStats {
  total: number;
  supply: number;
  demand: number;
  sourceChecks: number;
  metalCounts: Record<Metal, number>;
}

export interface ReportSummary {
  date: string;
  summary: string;
  searchText: string;
  stats: ReportStats;
}
