import fs from "node:fs";
import path from "node:path";

import type {
  DailyReport,
  Metal,
  ReportSignal,
  ReportStats,
  ReportSummary,
} from "@/lib/report-types";

const DATA_DIR = path.join(process.cwd(), "data");
const REPORT_FILE = /^\d{4}-\d{2}-\d{2}\.json$/;

export const METALS: Metal[] = ["gold", "silver", "copper"];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readReport(filename: string): DailyReport {
  const fullPath = path.join(DATA_DIR, filename);
  let parsed: unknown;

  try {
    parsed = JSON.parse(fs.readFileSync(fullPath, "utf8"));
  } catch (error) {
    throw new Error(
      `Invalid report JSON: ${filename}: ${error instanceof Error ? error.message : String(error)}`,
    );
  }

  if (
    !isRecord(parsed) ||
    typeof parsed.date !== "string" ||
    typeof parsed.report_time !== "string" ||
    !Array.isArray(parsed.part1_broadcasts) ||
    !Array.isArray(parsed.part2_x_posts) ||
    !Array.isArray(parsed.part3_news) ||
    !isRecord(parsed.windows) ||
    !isRecord(parsed.search_log) ||
    !isRecord(parsed.dedup_log)
  ) {
    throw new Error(`Report is missing required fields: ${filename}`);
  }

  if (`${parsed.date}.json` !== filename) {
    throw new Error(`Report date does not match filename: ${filename}`);
  }

  return parsed as unknown as DailyReport;
}

export function getReports(): DailyReport[] {
  return fs
    .readdirSync(DATA_DIR)
    .filter((filename) => REPORT_FILE.test(filename))
    .map(readReport)
    .sort((a, b) => b.date.localeCompare(a.date));
}

export function getReportByDate(date: string): DailyReport | undefined {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return undefined;
  const filename = `${date}.json`;
  return fs.existsSync(path.join(DATA_DIR, filename))
    ? readReport(filename)
    : undefined;
}

export function getSignals(report: DailyReport): ReportSignal[] {
  const broadcasts: ReportSignal[] = report.part1_broadcasts.map((item, index) => ({
    id: `broadcast-${index}`,
    kind: "Broadcast",
    title: item.title,
    source: item.guest?.name || item.source_type,
    publishedAt: item.publish_date,
    metalTags: item.metal_tags,
    direction: item.supply_demand,
    fact: item.summary,
    interpretation: item.detail || item.summary,
    importance: item.importance || "",
    url: item.url,
  }));

  const xPosts: ReportSignal[] = report.part2_x_posts.map((item, index) => ({
    id: `x-${index}`,
    kind: "X",
    title: `${item.author}（${item.handle}）`,
    source: item.handle,
    publishedAt: item.publish_time,
    metalTags: item.metal_tags,
    direction: item.supply_demand,
    fact: item.excerpt || "",
    interpretation: item.interpretation || "",
    importance: item.importance || "",
    url: item.url,
  }));

  const news: ReportSignal[] = report.part3_news.map((item, index) => ({
    id: `news-${index}`,
    kind: "News",
    title: item.title,
    source: item.source,
    publishedAt: item.publish_time,
    metalTags: item.metal_tags,
    direction: item.supply_demand,
    fact: item.excerpt || "",
    interpretation: item.interpretation || "",
    importance: item.importance || "",
    url: item.url,
    language: item.language,
  }));

  return [...broadcasts, ...xPosts, ...news].sort((a, b) =>
    b.publishedAt.localeCompare(a.publishedAt),
  );
}

export function getReportSummary(report: DailyReport): string {
  if (report.summary?.trim()) return report.summary.trim();
  const firstSignal = getSignals(report)[0];
  return (
    firstSignal?.importance ||
    firstSignal?.interpretation ||
    firstSignal?.fact ||
    "本期未发现符合筛选标准的新增供需信号。"
  );
}

export function getReportStats(report: DailyReport): ReportStats {
  const signals = getSignals(report);
  const metalCounts = { gold: 0, silver: 0, copper: 0 };

  for (const signal of signals) {
    for (const metal of signal.metalTags) metalCounts[metal] += 1;
  }

  const checked = [
    report.search_log.part1_sources_checked,
    report.search_log.part2_sources_checked,
    report.search_log.part3_sources_checked,
  ];

  return {
    total: signals.length,
    supply: signals.filter((signal) => signal.direction !== "demand").length,
    demand: signals.filter((signal) => signal.direction !== "supply").length,
    sourceChecks: checked.reduce((sum, list) => sum + (list?.length || 0), 0),
    metalCounts,
  };
}

export function getReportSummaries(): ReportSummary[] {
  return getReports().map((report) => {
    const signals = getSignals(report);
    const summary = getReportSummary(report);
    return {
      date: report.date,
      summary,
      searchText: [
        report.date,
        summary,
        ...signals.flatMap((signal) => [
          signal.title,
          signal.source,
          signal.metalTags.join(" "),
        ]),
      ].join(" "),
      stats: getReportStats(report),
    };
  });
}

export function getAdjacentReports(date: string): {
  older?: DailyReport;
  newer?: DailyReport;
} {
  const reports = getReports();
  const index = reports.findIndex((report) => report.date === date);
  if (index < 0) return {};
  return { older: reports[index + 1], newer: reports[index - 1] };
}

export function formatDate(date: string): string {
  const [year, month, day] = date.split("-").map(Number);
  return `${year}年${month}月${day}日`;
}

export function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

export function metalLabel(metal: Metal): string {
  return { gold: "黄金", silver: "白银", copper: "铜" }[metal];
}

export function directionLabel(direction: ReportSignal["direction"]): string {
  return { supply: "供给", demand: "需求", both: "供给与需求" }[direction];
}
