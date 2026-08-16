import fs from "node:fs";
import path from "node:path";

import {
  CURRENT_REPORT_SCHEMA_VERSION,
  type DailyReport,
  type Metal,
  type ReportSignal,
  type ReportStats,
  type ReportSummary,
} from "@/lib/report-types";
import { compareReportTimesDesc } from "@/lib/report-time";

const DATA_DIR = path.join(process.cwd(), "data");
const REPORT_FILE = /^\d{4}-\d{2}-\d{2}\.json$/;

export const METALS: Metal[] = ["copper", "gold", "silver"];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

const DATE_ONLY = /^(\d{4})-(\d{2})-(\d{2})$/;
const DATE_TIME = /^(\d{4}-\d{2}-\d{2})T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/;
const DIRECTIONS = new Set(["supply", "demand", "both"]);

function isCalendarDate(value: unknown): value is string {
  if (typeof value !== "string") return false;
  const match = DATE_ONLY.exec(value);
  if (!match) return false;
  const [, year, month, day] = match.map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return (
    parsed.getUTCFullYear() === year &&
    parsed.getUTCMonth() === month - 1 &&
    parsed.getUTCDate() === day
  );
}

function isDateTime(value: unknown): value is string {
  if (typeof value !== "string") return false;
  const match = DATE_TIME.exec(value);
  return Boolean(match && isCalendarDate(match[1]) && !Number.isNaN(Date.parse(value)));
}

function assertDate(value: unknown, field: string, filename: string): asserts value is string {
  if (!isCalendarDate(value)) throw new Error(`Invalid report date: ${filename}: ${field}`);
}

function assertDateTime(value: unknown, field: string, filename: string): asserts value is string {
  if (!isDateTime(value)) throw new Error(`Invalid report date-time: ${filename}: ${field}`);
}

function assertDateOrDateTime(value: unknown, field: string, filename: string): asserts value is string {
  if (!isCalendarDate(value) && !isDateTime(value)) {
    throw new Error(`Invalid report date: ${filename}: ${field}`);
  }
}

function assertUrl(value: unknown, field: string, filename: string): asserts value is string {
  if (typeof value !== "string") {
    throw new Error(`Invalid report URL: ${filename}: ${field}`);
  }
  try {
    const url = new URL(value);
    if (url.protocol !== "http:" && url.protocol !== "https:") throw new Error();
  } catch {
    throw new Error(`Invalid report URL: ${filename}: ${field}`);
  }
}

function assertClaims(value: Record<string, unknown>, field: string, filename: string): void {
  if (value.claims === undefined) return;
  if (!Array.isArray(value.claims)) {
    throw new Error(`Invalid report claims: ${filename}: ${field}.claims`);
  }
  value.claims.forEach((claim, index) => {
    if (!isRecord(claim)) {
      throw new Error(`Invalid report claim: ${filename}: ${field}.claims[${index}]`);
    }
    assertUrl(claim.source_url, `${field}.claims[${index}].source_url`, filename);
  });
}

function assertSignal(
  value: unknown,
  field: string,
  publishedField: "publish_date" | "publish_time",
  filename: string,
): asserts value is Record<string, unknown> {
  if (!isRecord(value)) throw new Error(`Invalid report signal: ${filename}: ${field}`);

  if (!Array.isArray(value.metal_tags) || value.metal_tags.length === 0) {
    throw new Error(`Invalid report signal: ${filename}: ${field}.metal_tags`);
  }
  for (const metal of value.metal_tags) {
    if (typeof metal !== "string" || !METALS.includes(metal as Metal)) {
      throw new Error(`Invalid report metal: ${filename}: ${field}.metal_tags`);
    }
  }
  if (value.primary_metal !== undefined) {
    if (
      typeof value.primary_metal !== "string" ||
      !METALS.includes(value.primary_metal as Metal) ||
      !value.metal_tags.includes(value.primary_metal)
    ) {
      throw new Error(`Invalid report primary metal: ${filename}: ${field}.primary_metal`);
    }
  }
  if (typeof value.supply_demand !== "string" || !DIRECTIONS.has(value.supply_demand)) {
    throw new Error(`Invalid report direction: ${filename}: ${field}.supply_demand`);
  }
  if (publishedField === "publish_date") {
    assertDate(value[publishedField], `${field}.${publishedField}`, filename);
  } else {
    assertDateOrDateTime(value[publishedField], `${field}.${publishedField}`, filename);
  }
  assertUrl(value.url, `${field}.url`, filename);
  assertClaims(value, field, filename);
}

export function parseReport(parsed: unknown, filename: string): DailyReport {
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

  assertDate(parsed.date, "date", filename);
  assertDateTime(parsed.report_time, "report_time", filename);
  if (`${parsed.date}.json` !== filename) {
    throw new Error(`Report date does not match filename: ${filename}`);
  }
  if (
    parsed.schema_version !== undefined &&
    parsed.schema_version !== CURRENT_REPORT_SCHEMA_VERSION
  ) {
    throw new Error(`Invalid report schema version: ${filename}`);
  }

  for (const part of ["part1", "part2", "part3"] as const) {
    const window = parsed.windows[part];
    if (!isRecord(window)) throw new Error(`Invalid report window: ${filename}: windows.${part}`);
    assertDateTime(window.start, `windows.${part}.start`, filename);
    assertDateTime(window.end, `windows.${part}.end`, filename);
  }

  parsed.part1_broadcasts.forEach((item, index) =>
    assertSignal(item, `part1_broadcasts[${index}]`, "publish_date", filename),
  );
  parsed.part2_x_posts.forEach((item, index) =>
    assertSignal(item, `part2_x_posts[${index}]`, "publish_time", filename),
  );
  parsed.part3_news.forEach((item, index) =>
    assertSignal(item, `part3_news[${index}]`, "publish_time", filename),
  );

  return parsed as unknown as DailyReport;
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

  return parseReport(parsed, filename);
}

export function getReports(): DailyReport[] {
  let filenames: string[];
  try {
    filenames = fs.readdirSync(DATA_DIR);
  } catch (error) {
    throw new Error(
      `Unable to read daily reports from data directory ${DATA_DIR}: ${error instanceof Error ? error.message : String(error)}`,
    );
  }

  const reports = filenames.filter((filename) => REPORT_FILE.test(filename)).map(readReport);
  if (!reports.length) {
    throw new Error(`No daily reports found in data directory ${DATA_DIR}`);
  }
  return reports.sort((a, b) => b.date.localeCompare(a.date));
}

export function getReportByDate(date: string): DailyReport | undefined {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return undefined;
  const filename = `${date}.json`;
  return fs.existsSync(path.join(DATA_DIR, filename))
    ? readReport(filename)
    : undefined;
}

export function getSignals(report: DailyReport): ReportSignal[] {
  // ponytail: Historical reports fall back to their first tag; this can only preserve
  // legacy ordering, not editorial intent. Remove the fallback after those reports are backfilled.
  const broadcasts: ReportSignal[] = report.part1_broadcasts.map((item, index) => ({
    id: `broadcast-${index}`,
    kind: "Broadcast",
    title: item.title,
    source: item.guest?.name || item.source_type,
    publishedAt: item.publish_date,
    metalTags: item.metal_tags,
    primaryMetal: item.primary_metal || item.metal_tags[0],
    direction: item.supply_demand,
    fact: item.summary,
    interpretation: item.detail || item.summary,
    importance: item.importance || "",
    verificationStatus: item.verification_status || (report.date < "2026-08-09" ? "verified" : "unverified"),
    verificationNote: item.verification_note || (report.date < "2026-08-09" ? "" : "核验状态缺失"),
    url: item.url,
  }));

  const xPosts: ReportSignal[] = report.part2_x_posts.map((item, index) => ({
    id: `x-${index}`,
    kind: "X",
    title: `${item.author}（${item.handle}）`,
    source: item.handle,
    publishedAt: item.publish_time,
    metalTags: item.metal_tags,
    primaryMetal: item.primary_metal || item.metal_tags[0],
    direction: item.supply_demand,
    fact: item.excerpt || "",
    interpretation: item.interpretation || "",
    importance: item.importance || "",
    verificationStatus: item.verification_status || (report.date < "2026-08-09" ? "verified" : "unverified"),
    verificationNote: item.verification_note || (report.date < "2026-08-09" ? "" : "核验状态缺失"),
    url: item.url,
  }));

  const news: ReportSignal[] = report.part3_news.map((item, index) => ({
    id: `news-${index}`,
    kind: "News",
    title: item.title,
    source: item.source,
    publishedAt: item.publish_time,
    metalTags: item.metal_tags,
    primaryMetal: item.primary_metal || item.metal_tags[0],
    direction: item.supply_demand,
    fact: item.excerpt || "",
    interpretation: item.interpretation || "",
    importance: item.importance || "",
    verificationStatus: item.verification_status || (report.date < "2026-08-09" ? "verified" : "unverified"),
    verificationNote: item.verification_note || (report.date < "2026-08-09" ? "" : "核验状态缺失"),
    url: item.url,
    language: item.language,
  }));

  return [...broadcasts, ...xPosts, ...news].sort((left, right) =>
    compareReportTimesDesc(left.publishedAt, right.publishedAt),
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

  for (const signal of signals) metalCounts[signal.primaryMetal] += 1;

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
          signal.fact,
          signal.interpretation,
          signal.importance,
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
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return formatDate(value);
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
