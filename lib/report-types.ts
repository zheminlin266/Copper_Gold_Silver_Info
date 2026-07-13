export type Metal = "gold" | "silver" | "copper";
export type SupplyDemand = "supply" | "demand" | "both";

export interface Broadcast {
  title: string;
  url: string;
  publish_date: string;
  source_type: string;
  metal_tags: Metal[];
  supply_demand: SupplyDemand;
  summary: string;
  detail?: string;
  importance?: string;
  guest?: { name?: string; background?: string };
  companies?: string[];
  projects?: string[];
}

export interface XPost {
  author: string;
  handle: string;
  publish_time: string;
  metal_tags: Metal[];
  supply_demand: SupplyDemand;
  excerpt?: string;
  interpretation?: string;
  importance?: string;
  url: string;
  source_channel?: string;
}

export interface NewsItem {
  source: string;
  title: string;
  url: string;
  publish_time: string;
  metal_tags: Metal[];
  supply_demand: SupplyDemand;
  excerpt?: string;
  interpretation?: string;
  importance?: string;
  language?: "en" | "zh";
  duplicate_of?: string | null;
}

export interface SearchLog {
  part1_searched?: boolean;
  part1_sources_checked?: string[];
  part1_result?: string;
  part2_searched?: boolean;
  part2_channel?: string;
  part2_sources_checked?: string[];
  part2_result?: string;
  part3_sources_checked?: string[];
  part3_result?: string;
  new_sources_discovered?: string[];
}

export interface DailyReport {
  date: string;
  report_time: string;
  summary?: string;
  windows: {
    part1: { start: string; end: string };
    part2: { start: string; end: string };
    part3: { start: string; end: string };
  };
  part1_broadcasts: Broadcast[];
  part2_x_posts: XPost[];
  part3_news: NewsItem[];
  search_log: SearchLog;
  dedup_log: {
    part1_deduped_urls?: string[];
    part3_deduped_events?: string[];
  };
}

export interface ReportSignal {
  id: string;
  kind: "Broadcast" | "X" | "News";
  title: string;
  source: string;
  publishedAt: string;
  metalTags: Metal[];
  direction: SupplyDemand;
  fact: string;
  interpretation: string;
  importance: string;
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
