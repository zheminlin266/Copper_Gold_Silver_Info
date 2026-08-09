export type Metal = "gold" | "silver" | "copper";
export type SupplyDemand = "supply" | "demand" | "both";
export type Part2Channel = "browser_use" | "rss_fallback" | "playwright" | "failed";
export type XSourceChannel = "browser_use" | "rss_fallback" | "playwright";
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

export interface SearchLog {
  part1_searched: boolean;
  part1_sources_checked?: string[];
  part1_result?: string;
  part2_searched: boolean;
  part2_channel?: Part2Channel;
  part2_sources_checked?: string[];
  part2_result?: string;
  part3_searched?: boolean;
  part3_sources_checked: string[];
  part3_result?: string;
  mining_com_source_note?: string;
  image_source?: ImageSource;
  new_sources_discovered?: string[];
  url_verification?: UrlVerification;
}

export interface DedupLog {
  part1_deduped_urls: string[];
  part2_deduped_urls?: string[];
  part3_deduped_events: string[];
  notes?: string;
}

export interface DailyReport {
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
