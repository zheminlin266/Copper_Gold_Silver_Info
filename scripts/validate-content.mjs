import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const DATE_FILE = /^\d{4}-\d{2}-\d{2}\.json$/;
const METALS = new Set(["gold", "silver", "copper"]);
const DIRECTIONS = new Set(["supply", "demand", "both"]);

function isObject(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireString(value, field, filename) {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${filename}: ${field} must be a non-empty string`);
  }
}

function validateUrl(value, field, filename) {
  requireString(value, field, filename);
  const url = new URL(value);
  if (!new Set(["http:", "https:"]).has(url.protocol)) {
    throw new Error(`${filename}: ${field} must use http or https`);
  }
}

function validateSignal(item, prefix, filename) {
  if (!isObject(item)) throw new Error(`${filename}: ${prefix} must be an object`);
  if (!Array.isArray(item.metal_tags) || item.metal_tags.length === 0) {
    throw new Error(`${filename}: ${prefix}.metal_tags must not be empty`);
  }
  for (const metal of item.metal_tags) {
    if (!METALS.has(metal)) throw new Error(`${filename}: ${prefix} has invalid metal ${metal}`);
  }
  if (!DIRECTIONS.has(item.supply_demand)) {
    throw new Error(`${filename}: ${prefix} has invalid supply_demand`);
  }
  validateUrl(item.url, `${prefix}.url`, filename);
}

export function validateReport(report, filename) {
  if (!isObject(report)) throw new Error(`${filename}: report must be an object`);
  requireString(report.date, "date", filename);
  requireString(report.report_time, "report_time", filename);
  if (`${report.date}.json` !== filename) {
    throw new Error(`${filename}: date does not match filename`);
  }
  if (Number.isNaN(Date.parse(report.report_time))) {
    throw new Error(`${filename}: report_time is not a valid ISO date-time`);
  }
  if (!isObject(report.windows) || !isObject(report.search_log) || !isObject(report.dedup_log)) {
    throw new Error(`${filename}: windows, search_log and dedup_log are required objects`);
  }

  for (const key of ["part1_broadcasts", "part2_x_posts", "part3_news"]) {
    if (!Array.isArray(report[key])) throw new Error(`${filename}: ${key} must be an array`);
    report[key].forEach((item, index) => validateSignal(item, `${key}[${index}]`, filename));
  }

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
