import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const DATE_FILE = /^\d{4}-\d{2}-\d{2}\.json$/;
const DATE = /^(\d{4})-(\d{2})-(\d{2})$/;
const METALS = new Set(["gold", "silver", "copper"]);
const DIRECTIONS = new Set(["supply", "demand", "both"]);
const SOURCE_TYPES = new Set([
  "podcast",
  "webcast",
  "youtube",
  "conference_interview",
  "panel",
  "keynote",
  "company_presentation",
]);
const PRIMARY_METAL_REQUIRED_FROM = "2026-07-14";

function isObject(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireString(value, field, filename) {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${filename}: ${field} must be a non-empty string`);
  }
}

function requireArray(value, field, filename) {
  if (!Array.isArray(value)) throw new Error(`${filename}: ${field} must be an array`);
}

function requireStringArray(value, field, filename) {
  requireArray(value, field, filename);
  value.forEach((item, index) => requireString(item, `${field}[${index}]`, filename));
}

function isCalendarDate(value) {
  const match = DATE.exec(value);
  if (!match) return false;
  const [, year, month, day] = match.map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return parsed.getUTCFullYear() === year
    && parsed.getUTCMonth() === month - 1
    && parsed.getUTCDate() === day;
}

function validateDate(value, field, filename) {
  requireString(value, field, filename);
  if (!isCalendarDate(value)) throw new Error(`${filename}: ${field} must be a real YYYY-MM-DD date`);
}

function validateDateTime(value, field, filename) {
  requireString(value, field, filename);
  if (!/T/.test(value) || Number.isNaN(Date.parse(value))) {
    throw new Error(`${filename}: ${field} must be a valid ISO date-time`);
  }
}

function validateDateOrDateTime(value, field, filename) {
  if (typeof value === "string" && isCalendarDate(value)) return;
  validateDateTime(value, field, filename);
}

function validateUrl(value, field, filename) {
  requireString(value, field, filename);
  let url;
  try {
    url = new URL(value);
  } catch {
    throw new Error(`${filename}: ${field} must be a valid URL`);
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error(`${filename}: ${field} must use http or https`);
  }
}

function validateSignal(item, prefix, filename, requirePrimaryMetal) {
  if (!isObject(item)) throw new Error(`${filename}: ${prefix} must be an object`);
  requireStringArray(item.metal_tags, `${prefix}.metal_tags`, filename);
  if (item.metal_tags.length === 0) {
    throw new Error(`${filename}: ${prefix}.metal_tags must not be empty`);
  }
  if (new Set(item.metal_tags).size !== item.metal_tags.length) {
    throw new Error(`${filename}: ${prefix}.metal_tags must not contain duplicates`);
  }
  for (const metal of item.metal_tags) {
    if (!METALS.has(metal)) throw new Error(`${filename}: ${prefix} has invalid metal ${metal}`);
  }
  if (requirePrimaryMetal && item.primary_metal === undefined) {
    throw new Error(`${filename}: ${prefix}.primary_metal is required`);
  }
  if (item.primary_metal !== undefined) {
    if (!METALS.has(item.primary_metal)) {
      throw new Error(`${filename}: ${prefix}.primary_metal is invalid`);
    }
    if (!item.metal_tags.includes(item.primary_metal)) {
      throw new Error(`${filename}: ${prefix}.primary_metal must also appear in metal_tags`);
    }
  }
  if (!DIRECTIONS.has(item.supply_demand)) {
    throw new Error(`${filename}: ${prefix} has invalid supply_demand`);
  }
  validateUrl(item.url, `${prefix}.url`, filename);
}

function validateBroadcast(item, prefix, filename, requirePrimaryMetal) {
  validateSignal(item, prefix, filename, requirePrimaryMetal);
  requireString(item.title, `${prefix}.title`, filename);
  validateDate(item.publish_date, `${prefix}.publish_date`, filename);
  requireString(item.source_type, `${prefix}.source_type`, filename);
  if (!SOURCE_TYPES.has(item.source_type)) {
    throw new Error(`${filename}: ${prefix}.source_type is unsupported`);
  }
  requireString(item.summary, `${prefix}.summary`, filename);
}

function validateXPost(item, prefix, filename, requirePrimaryMetal) {
  validateSignal(item, prefix, filename, requirePrimaryMetal);
  requireString(item.author, `${prefix}.author`, filename);
  requireString(item.handle, `${prefix}.handle`, filename);
  validateDateTime(item.publish_time, `${prefix}.publish_time`, filename);
}

function validateNews(item, prefix, filename, requirePrimaryMetal) {
  validateSignal(item, prefix, filename, requirePrimaryMetal);
  requireString(item.source, `${prefix}.source`, filename);
  requireString(item.title, `${prefix}.title`, filename);
  validateDateOrDateTime(item.publish_time, `${prefix}.publish_time`, filename);
  if (item.language !== "en" && item.language !== "zh") {
    throw new Error(`${filename}: ${prefix}.language must be en or zh`);
  }
}

function validateWindow(window, field, filename) {
  if (!isObject(window)) throw new Error(`${filename}: ${field} must be an object`);
  validateDateTime(window.start, `${field}.start`, filename);
  validateDateTime(window.end, `${field}.end`, filename);
  if (Date.parse(window.start) > Date.parse(window.end)) {
    throw new Error(`${filename}: ${field}.start must not be after end`);
  }
}

export function validateReport(report, filename) {
  if (!isObject(report)) throw new Error(`${filename}: report must be an object`);
  validateDate(report.date, "date", filename);
  validateDateTime(report.report_time, "report_time", filename);
  requireString(report.summary, "summary", filename);
  if (`${report.date}.json` !== filename) {
    throw new Error(`${filename}: date does not match filename`);
  }
  const requirePrimaryMetal = report.date >= PRIMARY_METAL_REQUIRED_FROM;

  if (!isObject(report.windows)) throw new Error(`${filename}: windows must be an object`);
  for (const part of ["part1", "part2", "part3"]) {
    validateWindow(report.windows[part], `windows.${part}`, filename);
  }

  requireArray(report.part1_broadcasts, "part1_broadcasts", filename);
  report.part1_broadcasts.forEach((item, index) => validateBroadcast(item, `part1_broadcasts[${index}]`, filename, requirePrimaryMetal));
  requireArray(report.part2_x_posts, "part2_x_posts", filename);
  report.part2_x_posts.forEach((item, index) => validateXPost(item, `part2_x_posts[${index}]`, filename, requirePrimaryMetal));
  requireArray(report.part3_news, "part3_news", filename);
  report.part3_news.forEach((item, index) => validateNews(item, `part3_news[${index}]`, filename, requirePrimaryMetal));

  if (!isObject(report.search_log)) throw new Error(`${filename}: search_log must be an object`);
  if (typeof report.search_log.part1_searched !== "boolean") {
    throw new Error(`${filename}: search_log.part1_searched must be boolean`);
  }
  if (typeof report.search_log.part2_searched !== "boolean") {
    throw new Error(`${filename}: search_log.part2_searched must be boolean`);
  }
  requireStringArray(report.search_log.part3_sources_checked, "search_log.part3_sources_checked", filename);

  if (!isObject(report.dedup_log)) throw new Error(`${filename}: dedup_log must be an object`);
  requireStringArray(report.dedup_log.part1_deduped_urls, "dedup_log.part1_deduped_urls", filename);
  requireStringArray(report.dedup_log.part3_deduped_events, "dedup_log.part3_deduped_events", filename);

  return report;
}

export function loadReports(dataDir = path.join(process.cwd(), "data")) {
  const reports = [];
  for (const filename of fs.readdirSync(dataDir).filter((name) => DATE_FILE.test(name)).sort()) {
    const fullPath = path.join(dataDir, filename);
    let report;
    try {
      report = JSON.parse(fs.readFileSync(fullPath, "utf8"));
    } catch (error) {
      throw new Error(`${filename}: invalid JSON: ${error.message}`);
    }
    reports.push(validateReport(report, filename));
  }
  if (!reports.length) throw new Error("No daily report JSON files found");
  return reports;
}

function main() {
  const reports = loadReports();
  console.log(`Validated ${reports.length} daily reports (${reports[0].date} to ${reports.at(-1).date}).`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  main();
}
