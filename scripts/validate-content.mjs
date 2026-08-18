import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

const DATE_FILE = /^\d{4}-\d{2}-\d{2}\.json$/;
const DATE = /^(\d{4})-(\d{2})-(\d{2})$/;
const DATE_TIME = /^(\d{4}-\d{2}-\d{2})T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/;
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
const IMPORTANCE_VALIDATED_FROM = "2026-07-31";
const COLLECTION_COMPLETENESS_REQUIRED_FROM = "2026-08-09";
const VERIFICATION_STATUS_REQUIRED_FROM = "2026-08-09";
const WINDOW_BOUNDARY_REQUIRED_FROM = "2026-07-06";
const PUBLISH_WINDOW_REQUIRED_FROM = "2026-07-06";
// These four published historical values stay fixed because moving them would change historical semantics.
const PUBLISH_WINDOW_EXCEPTIONS = new Map([
  ["2026-07-11.json|part3_news[0].publish_time", "2026-07-10T20:00:00+08:00"],
  ["2026-07-11.json|part3_news[1].publish_time", "2026-07-10T20:00:00+08:00"],
  ["2026-08-04.json|part3_news[0].publish_time", "2026-08-04T12:51:00-07:00"],
  ["2026-08-04.json|part3_news[3].publish_time", "2026-08-04T13:33:00-07:00"],
]);
const URL_VERIFICATION_REQUIRED_FROM = "2026-07-12";
const REPLACEMENT_CHARACTER_REQUIRED_FROM = "2026-08-09";
const IMPORTANCE_MIN_LENGTH = 80;
const IMPORTANCE_MAX_LENGTH = 300;
const SUMMARY_MAX_LENGTH = 300;
const IMPORTANCE_SENTENCE_END = /[。！？!?]/g;
const IMPORTANCE_CONCRETE_ANCHOR = /(?:\d|[一二三四五六七八九十百千万亿]+(?:吨|盎司|美元|年|月|周|天|季度)|(?:短期|中期|长期|即期|年内|下半年|未来\d+年|未来[一二三四五六七八九十百千万亿]+年)|(?:同比|环比|较前期|相比|连续第|首次|创(?:历史|新)?高|指引|投产|复产|许可|时间表|里程碑|钻探|扩建))/u;
const IMPORTANCE_ANALYSIS_MARKER = /(?:意味着|由于|因此|导致|通过|取决于|相较|相比|背景下|可能|风险|缺口|压力|增量|约束|兑现|传导|影响|支撑|限制|条件|提高|下降|上升|减少|增加|接近|低于|高于|维持|延长|缩短|释放|取代|验证|显示|反映|强化|削弱|改变|体现)/u;
const GENERIC_IMPORTANCE_ONLY = /^(?:这是|属于|可作为|补充了|反映了|提示|显示).{0,60}(?:信号|线索|风险|变化|判断)[。！？!?]$/u;

const SCHEMA_PATH = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "data", "daily_report_schema.json");
const schema = JSON.parse(fs.readFileSync(SCHEMA_PATH, "utf8"));
const ajv = new Ajv2020({ allErrors: true, strict: false });
addFormats(ajv);
const validateSchema = ajv.compile(schema);

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
  const match = DATE_TIME.exec(value);
  if (!match || !isCalendarDate(match[1]) || Number.isNaN(Date.parse(value))) {
    throw new Error(`${filename}: ${field} must be a valid ISO date-time with a timezone`);
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

function validateImportance(value, field, filename) {
  requireString(value, field, filename);
  const length = [...value].length;
  if (length < IMPORTANCE_MIN_LENGTH || length > IMPORTANCE_MAX_LENGTH) {
    throw new Error(
      `${filename}: ${field} must be ${IMPORTANCE_MIN_LENGTH}-${IMPORTANCE_MAX_LENGTH} characters for new reports`,
    );
  }

  const sentenceCount = value.match(IMPORTANCE_SENTENCE_END)?.length ?? 0;
  if (sentenceCount < 2 || sentenceCount > 4) {
    throw new Error(`${filename}: ${field} must contain 2-4 sentences for new reports`);
  }
  if (!IMPORTANCE_CONCRETE_ANCHOR.test(value)) {
    throw new Error(`${filename}: ${field} must contain a concrete anchor for new reports`);
  }
  if (!IMPORTANCE_ANALYSIS_MARKER.test(value) || GENERIC_IMPORTANCE_ONLY.test(value.trim())) {
    throw new Error(`${filename}: ${field} must contain analysis, not only a generic label`);
  }
}

function validateSignal(
  item,
  prefix,
  filename,
  requirePrimaryMetal,
  validateImportanceContent,
  requireVerificationStatus,
) {
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
  if (validateImportanceContent && item.importance !== undefined) {
    validateImportance(item.importance, `${prefix}.importance`, filename);
  }
  if (requireVerificationStatus && item.verification_status === undefined) {
    throw new Error(`${filename}: ${prefix}.verification_status is required`);
  }
  if (item.verification_status === "unverified") {
    requireString(item.verification_note, `${prefix}.verification_note`, filename);
  }
}

function validateBroadcast(item, prefix, filename, requirePrimaryMetal, validateImportanceContent, requireVerificationStatus) {
  validateSignal(item, prefix, filename, requirePrimaryMetal, validateImportanceContent, requireVerificationStatus);
  requireString(item.title, `${prefix}.title`, filename);
  validateDate(item.publish_date, `${prefix}.publish_date`, filename);
  requireString(item.source_type, `${prefix}.source_type`, filename);
  if (!SOURCE_TYPES.has(item.source_type)) {
    throw new Error(`${filename}: ${prefix}.source_type is unsupported`);
  }
  requireString(item.summary, `${prefix}.summary`, filename);
}

function validateXPost(item, prefix, filename, requirePrimaryMetal, validateImportanceContent, requireVerificationStatus) {
  validateSignal(item, prefix, filename, requirePrimaryMetal, validateImportanceContent, requireVerificationStatus);
  requireString(item.author, `${prefix}.author`, filename);
  requireString(item.handle, `${prefix}.handle`, filename);
  validateDateOrDateTime(item.publish_time, `${prefix}.publish_time`, filename);
}

function validateNews(item, prefix, filename, requirePrimaryMetal, validateImportanceContent, requireVerificationStatus) {
  validateSignal(item, prefix, filename, requirePrimaryMetal, validateImportanceContent, requireVerificationStatus);
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

function addCalendarDays(value, days) {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day + days)).toISOString().slice(0, 10);
}

function validateWindowBoundaries(report, filename) {
  if (report.date < WINDOW_BOUNDARY_REQUIRED_FROM) return;
  const expected = {
    part1: [addCalendarDays(report.date, -2), report.date],
    part2: [report.date, report.date],
    part3: [report.date, report.date],
  };
  for (const [part, [startDate, endDate]] of Object.entries(expected)) {
    const expectedStart = `${startDate}T00:00:00+08:00`;
    const expectedEnd = `${endDate}T23:59:59+08:00`;
    if (report.windows[part].start !== expectedStart || report.windows[part].end !== expectedEnd) {
      throw new Error(`${filename}: windows.${part} must be ${expectedStart} through ${expectedEnd}`);
    }
  }
}

function validatePublishedAt(value, window, field, filename) {
  const outsideWindow = isCalendarDate(value)
    ? value < window.start.slice(0, 10) || value > window.end.slice(0, 10)
    : Date.parse(value) < Date.parse(window.start) || Date.parse(value) > Date.parse(window.end);
  const exceptionValue = PUBLISH_WINDOW_EXCEPTIONS.get(`${filename}|${field}`);
  if (outsideWindow && exceptionValue !== value) {
    throw new Error(`${filename}: ${field} is outside its validation window`);
  }
}

function validatePublishedAtWindows(report, filename) {
  if (report.date < PUBLISH_WINDOW_REQUIRED_FROM) return;
  report.part1_broadcasts.forEach((item, index) => {
    validatePublishedAt(item.publish_date, report.windows.part1, `part1_broadcasts[${index}].publish_date`, filename);
  });
  report.part2_x_posts.forEach((item, index) => {
    validatePublishedAt(item.publish_time, report.windows.part2, `part2_x_posts[${index}].publish_time`, filename);
  });
  report.part3_news.forEach((item, index) => {
    validatePublishedAt(item.publish_time, report.windows.part3, `part3_news[${index}].publish_time`, filename);
  });
}

function validateUrlVerification(report, filename) {
  if (report.date < URL_VERIFICATION_REQUIRED_FROM) return;
  const verification = report.search_log.url_verification;
  if (!isObject(verification)) {
    throw new Error(`${filename}: search_log.url_verification is required from ${URL_VERIFICATION_REQUIRED_FROM}`);
  }
  for (const field of ["checked", "passed", "failed"]) {
    if (!Number.isInteger(verification[field]) || verification[field] < 0) {
      throw new Error(`${filename}: search_log.url_verification.${field} must be a non-negative integer`);
    }
  }
  if (verification.checked !== verification.passed + verification.failed) {
    throw new Error(`${filename}: search_log.url_verification.checked must equal passed + failed`);
  }
  const failures = verification.failures ?? [];
  if (verification.failed > 0 && failures.length === 0) {
    throw new Error(`${filename}: search_log.url_verification.failures must be non-empty when failed > 0`);
  }
}

function validateCollectionCompleteness(report, filename) {
  if (report.date < COLLECTION_COMPLETENESS_REQUIRED_FROM) return;
  for (const part of ["part1", "part2", "part3"]) {
    const searchedField = `${part}_searched`;
    if (report.search_log[searchedField] !== true) {
      throw new Error(
        `${filename}: search_log.${searchedField} must be true; failed collection cannot be published as zero results`,
      );
    }
    requireStringArray(
      report.search_log[`${part}_sources_checked`],
      `search_log.${part}_sources_checked`,
      filename,
    );
    requireString(report.search_log[`${part}_result`], `search_log.${part}_result`, filename);
  }
  if (!new Set(["twscrape", "playwright"]).has(report.search_log.part2_channel)) {
    throw new Error(
      `${filename}: search_log.part2_channel must be twscrape or playwright after successful X collection`,
    );
  }
}

function validateVerificationCoverage(report, filename) {
  if (report.date < VERIFICATION_STATUS_REQUIRED_FROM) return;
  const signals = [
    ...report.part1_broadcasts,
    ...report.part2_x_posts,
    ...report.part3_news,
  ];
  const verified = signals.filter((item) => item.verification_status === "verified").length;
  const unverifiedItems = signals.filter((item) => item.verification_status === "unverified");
  const verification = report.search_log.url_verification;
  if (verification.passed < verified) {
    throw new Error(`${filename}: search_log.url_verification.passed must cover verified signals`);
  }
  if (verification.failed < unverifiedItems.length) {
    throw new Error(`${filename}: search_log.url_verification.failed must cover unverified signals`);
  }
  const failedUrls = new Set(
    (verification.failures ?? [])
      .filter((failure) => isObject(failure) && typeof failure.url === "string")
      .map((failure) => failure.url),
  );
  for (const item of unverifiedItems) {
    if (!failedUrls.has(item.url)) {
      throw new Error(
        `${filename}: search_log.url_verification.failures must list unverified URL ${item.url}`,
      );
    }
  }
}

function rejectReplacementCharacters(value, field, filename) {
  if (typeof value === "string") {
    if (value.includes("\ufffd")) throw new Error(`${filename}: ${field} must not contain U+FFFD replacement character`);
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item, index) => rejectReplacementCharacters(item, `${field}[${index}]`, filename));
    return;
  }
  if (isObject(value)) {
    Object.entries(value).forEach(([key, item]) => rejectReplacementCharacters(item, `${field}.${key}`, filename));
  }
}

function formatSchemaError(error, filename) {
  const instancePath = error.instancePath || "/";
  const message = error.keyword === "format"
    && error.params?.format === "date-time"
    && instancePath.endsWith("/publish_time")
    ? "must be a valid ISO date-time with a timezone"
    : error.keyword === "maxLength" && instancePath === "/summary"
      ? "summary must be no more than 300 characters"
      : error.message;
  return `${filename}: ${instancePath} ${message}`;
}

function validateSchemaOrThrow(report, filename) {
  if (validateSchema(report)) return;
  const details = (validateSchema.errors ?? []).map((error) => formatSchemaError(error, filename));
  throw new Error([`${filename}: JSON Schema validation failed`, ...details].join("\n"));
}

export function validateReport(report, filename) {
  validateSchemaOrThrow(report, filename);
  if (!isObject(report)) throw new Error(`${filename}: report must be an object`);
  validateDate(report.date, "date", filename);
  validateDateTime(report.report_time, "report_time", filename);
  requireString(report.summary, "summary", filename);
  if ([...report.summary].length > SUMMARY_MAX_LENGTH) {
    throw new Error(`${filename}: summary must be no more than ${SUMMARY_MAX_LENGTH} characters`);
  }
  if (`${report.date}.json` !== filename) {
    throw new Error(`${filename}: date does not match filename`);
  }
  const requirePrimaryMetal = report.date >= PRIMARY_METAL_REQUIRED_FROM;
  const validateImportanceContent = report.date >= IMPORTANCE_VALIDATED_FROM;
  const requireVerificationStatus = report.date >= VERIFICATION_STATUS_REQUIRED_FROM;

  if (!isObject(report.windows)) throw new Error(`${filename}: windows must be an object`);
  for (const part of ["part1", "part2", "part3"]) {
    validateWindow(report.windows[part], `windows.${part}`, filename);
  }
  validateWindowBoundaries(report, filename);

  requireArray(report.part1_broadcasts, "part1_broadcasts", filename);
  report.part1_broadcasts.forEach((item, index) => validateBroadcast(
    item,
    `part1_broadcasts[${index}]`,
    filename,
    requirePrimaryMetal,
    validateImportanceContent,
    requireVerificationStatus,
  ));
  requireArray(report.part2_x_posts, "part2_x_posts", filename);
  report.part2_x_posts.forEach((item, index) => validateXPost(
    item,
    `part2_x_posts[${index}]`,
    filename,
    requirePrimaryMetal,
    validateImportanceContent,
    requireVerificationStatus,
  ));
  requireArray(report.part3_news, "part3_news", filename);
  report.part3_news.forEach((item, index) => validateNews(
    item,
    `part3_news[${index}]`,
    filename,
    requirePrimaryMetal,
    validateImportanceContent,
    requireVerificationStatus,
  ));
  validatePublishedAtWindows(report, filename);

  if (!isObject(report.search_log)) throw new Error(`${filename}: search_log must be an object`);
  if (typeof report.search_log.part1_searched !== "boolean") {
    throw new Error(`${filename}: search_log.part1_searched must be boolean`);
  }
  if (typeof report.search_log.part2_searched !== "boolean") {
    throw new Error(`${filename}: search_log.part2_searched must be boolean`);
  }
  requireStringArray(report.search_log.part3_sources_checked, "search_log.part3_sources_checked", filename);
  validateCollectionCompleteness(report, filename);
  validateUrlVerification(report, filename);
  validateVerificationCoverage(report, filename);

  if (!isObject(report.dedup_log)) throw new Error(`${filename}: dedup_log must be an object`);
  requireStringArray(report.dedup_log.part1_deduped_urls, "dedup_log.part1_deduped_urls", filename);
  requireStringArray(report.dedup_log.part3_deduped_events, "dedup_log.part3_deduped_events", filename);

  if (report.date >= REPLACEMENT_CHARACTER_REQUIRED_FROM) {
    rejectReplacementCharacters(report, "$", filename);
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
