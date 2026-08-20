import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

import { getArchivePage, REPORTS_PER_PAGE } from "../lib/archive-pagination.ts";
import { compareReportTimesDesc } from "../lib/report-time.ts";
import { parseTcCsv } from "../lib/tc-data.ts";
import { loadReports, validateReport } from "../scripts/validate-content.mjs";

function makeFutureReport() {
  const report = JSON.parse(
    fs.readFileSync(path.join(process.cwd(), "data", "2026-08-08.json"), "utf8"),
  );
  report.date = "2026-08-09";
  report.windows = {
    part1: { start: "2026-08-07T00:00:00+08:00", end: "2026-08-09T23:59:59+08:00" },
    part2: { start: "2026-08-09T00:00:00+08:00", end: "2026-08-09T23:59:59+08:00" },
    part3: { start: "2026-08-09T00:00:00+08:00", end: "2026-08-09T23:59:59+08:00" },
  };
  report.search_log.part2_channel = "playwright";
  report.search_log.part3_searched = true;
  return report;
}

test("new X coverage audit accepts partial reports and rejects count conflicts", () => {
  const report = JSON.parse(fs.readFileSync(path.join(process.cwd(), "data", "2026-08-08.json"), "utf8"));
  report.date = "2026-08-19";
  report.windows = {
    part1: { start: "2026-08-17T00:00:00+08:00", end: "2026-08-19T23:59:59+08:00" },
    part2: { start: "2026-08-19T00:00:00+08:00", end: "2026-08-19T23:59:59+08:00" },
    part3: { start: "2026-08-19T00:00:00+08:00", end: "2026-08-19T23:59:59+08:00" },
  };
  report.part1_broadcasts.forEach((item) => { item.publish_date = "2026-08-18"; });
  report.part2_x_posts.forEach((item) => { item.publish_time = "2026-08-19"; });
  report.part3_news.forEach((item) => { item.publish_time = "2026-08-19"; });
  report.search_log.part1_searched = true;
  report.search_log.part3_searched = true;
  report.search_log.part2_searched = false;
  report.search_log.part2_channel = "twscrape";
  report.search_log.part2_result = "X coverage 1/2; one account failed";
  report.search_log.part2_coverage = {
    status: "partial", accounts_total: 2, accounts_completed: 1, accounts_failed: 1,
    attempted_channels: ["web_access_xai", "twscrape"], selected_channel: "web_access_xai+twscrape",
    channel_errors: ["one account failed"], notes: "candidate set preserved",
  };
  assert.doesNotThrow(() => validateReport(report, "2026-08-19.json"));
  report.search_log.part2_coverage.accounts_failed = 0;
  assert.throws(() => validateReport(report, "2026-08-19.json"), /counts must sum/);
});

test("current X coverage requires Playwright then twscrape and rejects web-access", () => {
  const report = JSON.parse(fs.readFileSync(path.join(process.cwd(), "data", "2026-08-08.json"), "utf8"));
  report.date = "2026-08-20";
  report.windows = {
    part1: { start: "2026-08-18T00:00:00+08:00", end: "2026-08-20T23:59:59+08:00" },
    part2: { start: "2026-08-20T00:00:00+08:00", end: "2026-08-20T23:59:59+08:00" },
    part3: { start: "2026-08-20T00:00:00+08:00", end: "2026-08-20T23:59:59+08:00" },
  };
  report.part1_broadcasts.forEach((item) => { item.publish_date = "2026-08-19"; });
  report.part2_x_posts.forEach((item) => { item.publish_time = "2026-08-20"; });
  report.part3_news.forEach((item) => { item.publish_time = "2026-08-20"; });
  report.search_log.part1_searched = true;
  report.search_log.part3_searched = true;
  report.search_log.part2_searched = false;
  report.search_log.part2_channel = "twscrape";
  report.search_log.part2_result = "X coverage 1/2; one account failed";
  report.search_log.part2_coverage = {
    status: "partial", accounts_total: 2, accounts_completed: 1, accounts_failed: 1,
    attempted_channels: ["playwright", "twscrape"], selected_channel: "playwright+twscrape",
    channel_errors: ["one account failed"], notes: "candidate set preserved",
  };
  assert.doesNotThrow(() => validateReport(report, "2026-08-20.json"));
  report.search_log.part2_coverage.attempted_channels = ["web_access_xai"];
  report.search_log.part2_coverage.selected_channel = "web_access_xai";
  assert.throws(() => validateReport(report, "2026-08-20.json"), /ordered channel prefix/);
});

test("archive pagination shows 20 newest items before older pages", () => {
  const reports = Array.from({ length: 45 }, (_, index) => `report-${index + 1}`);
  const first = getArchivePage(reports, 1);
  const second = getArchivePage(reports, 2);
  const last = getArchivePage(reports, 3);

  assert.equal(REPORTS_PER_PAGE, 20);
  assert.deepEqual(first.items, reports.slice(0, 20));
  assert.deepEqual(second.items, reports.slice(20, 40));
  assert.deepEqual(last.items, reports.slice(40, 45));
  assert.equal(last.pageCount, 3);
});

test("report time sorting uses timezone instants and Beijing midnight for date-only values", () => {
  const values = [
    "2026-01-01",
    "2025-12-31T17:00:00Z",
    "2025-12-31T16:00:00Z",
    "2026-01-01T00:00:00+08:00",
  ];

  assert.deepEqual(values.sort(compareReportTimesDesc), [
    "2025-12-31T17:00:00Z",
    "2026-01-01",
    "2025-12-31T16:00:00Z",
    "2026-01-01T00:00:00+08:00",
  ]);
  assert.ok(compareReportTimesDesc("not-a-time", "2026-01-01") > 0);
});

test("all daily reports are valid and uniquely dated", () => {
  const reports = loadReports();
  const dates = reports.map((report) => report.date);
  assert.equal(new Set(dates).size, dates.length);
  assert.deepEqual(dates, [...dates].sort());
});

test("TC CSV parsing validates, sorts, and preserves quoted source notes", () => {
  const csv = [
    "assessment_date,value_usd_per_dmt,change_usd_per_dmt,source_url,source_note",
    '2026-01-16,-46.53,-1.12,https://example.com/2,"weekly review, verified"',
    "2026-01-09,-45.41,-0.43,https://example.com/1,direct review",
  ].join("\n");

  const points = parseTcCsv(csv);
  assert.deepEqual(points.map((point) => point.assessmentDate), ["2026-01-09", "2026-01-16"]);
  assert.equal(points[1].sourceNote, "weekly review, verified");
  assert.equal(points[1].value, -46.53);

  assert.throws(
    () => parseTcCsv(`${csv}\n2026-01-16,-47,-0.47,https://example.com/3,duplicate`),
    /duplicate assessment_date/,
  );
});

test("daily summaries stay within the 300-character editorial limit", () => {
  const filename = "2026-07-14.json";
  const report = JSON.parse(fs.readFileSync(path.join(process.cwd(), "data", filename), "utf8"));
  const tooLong = structuredClone(report);
  tooLong.summary = "铜".repeat(301);

  assert.throws(
    () => validateReport(tooLong, filename),
    /summary must be no more than 300 characters/,
  );
});

test("provided importance judgments must be substantive while source-only cards remain valid", () => {
  const legacyFilename = "2026-07-30.json";
  const legacyReport = JSON.parse(
    fs.readFileSync(path.join(process.cwd(), "data", legacyFilename), "utf8"),
  );
  assert.doesNotThrow(() => validateReport(legacyReport, legacyFilename));

  const filename = "2026-07-31.json";
  const report = structuredClone(legacyReport);
  report.date = "2026-07-31";
  report.windows = {
    part1: { start: "2026-07-29T00:00:00+08:00", end: "2026-07-31T23:59:59+08:00" },
    part2: { start: "2026-07-31T00:00:00+08:00", end: "2026-07-31T23:59:59+08:00" },
    part3: { start: "2026-07-31T00:00:00+08:00", end: "2026-07-31T23:59:59+08:00" },
  };
  report.part2_x_posts.forEach((item) => { item.publish_time = "2026-07-31"; });
  report.part3_news.forEach((item) => { item.publish_time = "2026-07-31"; });
  const validImportance =
    "该矿二季度实际铜产量达到100,487吨，且库存矿石已开始转化为可销售精矿，短期增加了市场可见供给。由于这部分产量来自库存处理而不是采矿恢复，中期供给改善仍取决于设备修复和矿山重启；后续应跟踪处理持续时间、品位和实际发运量。";
  for (const signal of [
    ...report.part1_broadcasts,
    ...report.part2_x_posts,
    ...report.part3_news,
  ]) {
    signal.importance = validImportance;
  }

  const sourceOnly = structuredClone(report);
  delete sourceOnly.part3_news[0].excerpt;
  delete sourceOnly.part3_news[0].interpretation;
  delete sourceOnly.part3_news[0].importance;
  assert.doesNotThrow(() => validateReport(sourceOnly, filename));

  const short = structuredClone(report);
  short.part3_news[0].importance = "这是一个重要的铜供给信号。";
  assert.throws(
    () => validateReport(short, filename),
    /importance must be 80-300 characters for new reports/,
  );

  const oneSentence = structuredClone(report);
  oneSentence.part3_news[0].importance = validImportance.replace("。由于", "，由于");
  assert.throws(
    () => validateReport(oneSentence, filename),
    /importance must contain 2-4 sentences for new reports/,
  );

  const noConcreteAnchor = structuredClone(report);
  noConcreteAnchor.part3_news[0].importance =
    "这个项目会改变相关市场的供需预期，并可能提高参与者对未来变化的关注程度。它的影响仍然需要结合更多材料进行分析，当前不宜作出过度结论，也不能仅凭当前材料判断具体结果。";
  assert.throws(
    () => validateReport(noConcreteAnchor, filename),
    /importance must contain a concrete anchor for new reports/,
  );

  const substantive = structuredClone(report);
  assert.doesNotThrow(() => validateReport(substantive, filename));
});

test("production font loading stays local and build-safe", () => {
  const layout = fs.readFileSync(path.join(process.cwd(), "app", "layout.tsx"), "utf8");
  const localFont = path.join(process.cwd(), "assets", "fonts", "Geist-Regular.ttf");

  assert.match(layout, /next\/font\/local/);
  assert.doesNotMatch(layout, /next\/font\/google/);
  assert.ok(fs.existsSync(localFont), "local production font is missing");
});

test("publish_time accepts dates but rejects date-times without a timezone", () => {
  const filename = "2026-07-14.json";
  const report = JSON.parse(fs.readFileSync(path.join(process.cwd(), "data", filename), "utf8"));

  const xDateOnly = structuredClone(report);
  xDateOnly.part2_x_posts[0].publish_time = "2026-07-14";
  assert.doesNotThrow(() => validateReport(xDateOnly, filename));

  const newsDateOnly = structuredClone(report);
  newsDateOnly.part3_news[0].publish_time = "2026-07-14";
  assert.doesNotThrow(() => validateReport(newsDateOnly, filename));

  const missingTimezone = structuredClone(report);
  missingTimezone.part2_x_posts[0].publish_time = "2026-07-14T22:02:59";
  assert.throws(
    () => validateReport(missingTimezone, filename),
    /publish_time must be a valid ISO date-time with a timezone/,
  );
});

test("Ajv schema rejects legacy guest strings and unknown fields", () => {
  const filename = "2026-07-31.json";
  const base = JSON.parse(fs.readFileSync(path.join(process.cwd(), "data", filename), "utf8"));

  const stringGuest = structuredClone(base);
  stringGuest.part1_broadcasts[0].guest = "legacy guest";
  assert.throws(
    () => validateReport(stringGuest, filename),
    /2026-07-31\.json: \/part1_broadcasts\/0\/guest .*must be object/,
  );

  const unknownField = structuredClone(base);
  unknownField.unexpected = true;
  assert.throws(
    () => validateReport(unknownField, filename),
    /2026-07-31\.json: \/ .*must NOT have additional properties/,
  );
});

test("optional schema version and evidence claims preserve the report contract", () => {
  const filename = "2026-07-31.json";
  const report = JSON.parse(fs.readFileSync(path.join(process.cwd(), "data", filename), "utf8"));
  const claim = {
    claim: "铜项目将在2028年投产",
    evidence: "公司披露目标投产年份为2028年。",
    source_url: "https://example.com/source",
    evidence_type: "reported_fact",
    period: "2028",
    unit: "year",
    value: 2028,
  };

  const current = structuredClone(report);
  current.schema_version = 3;
  current.part3_news[0].claims = [claim];
  assert.doesNotThrow(() => validateReport(current, filename));

  const legacy = structuredClone(report);
  assert.doesNotThrow(() => validateReport(legacy, filename));

  const invalidVersion = structuredClone(current);
  invalidVersion.schema_version = 2;
  assert.throws(() => validateReport(invalidVersion, filename), /must be equal to constant/);

  const invalidClaim = structuredClone(current);
  invalidClaim.part3_news[0].claims[0].unexpected = true;
  assert.throws(
    () => validateReport(invalidClaim, filename),
    /claims\/0 .*must NOT have additional properties/,
  );
});

test("runtime report parsing rejects malformed dates, signals, and URLs before casting", () => {
  const filename = "2026-07-31.json";
  const base = JSON.parse(fs.readFileSync(path.join(process.cwd(), "data", filename), "utf8"));
  const cases = [
    ["invalid date", (report) => { report.date = "2026-02-30"; }, /date/],
    ["empty metal tags", (report) => { report.part3_news[0].metal_tags = []; }, /metal_tags/],
    ["invalid metal", (report) => { report.part3_news[0].metal_tags = ["tin"]; }, /metal_tags/],
    ["invalid direction", (report) => { report.part3_news[0].supply_demand = "neutral"; }, /supply_demand/],
    ["invalid primary metal", (report) => { report.part3_news[0].primary_metal = "tin"; }, /primary_metal/],
    ["invalid URL", (report) => { report.part3_news[0].url = "javascript:alert(1)"; }, /url/],
  ];

  for (const [name, mutate, pattern] of cases) {
    const malformed = structuredClone(base);
    mutate(malformed);
    assert.throws(() => validateReport(malformed, filename), pattern, name);
  }
});

test("post-migration window boundaries are exact", () => {
  const filename = "2026-07-06.json";
  const report = JSON.parse(fs.readFileSync(path.join(process.cwd(), "data", filename), "utf8"));
  report.windows.part1.start = "2026-07-03T00:00:00+08:00";

  assert.throws(
    () => validateReport(report, filename),
    /2026-07-06\.json: windows\.part1 must be/,
  );
});

test("reports from 2026-08-09 reject publish times outside their windows", () => {
  const report = makeFutureReport();
  const source = JSON.parse(fs.readFileSync(path.join(process.cwd(), "data", "2026-08-07.json"), "utf8"));
  report.part3_news = [structuredClone(source.part3_news[0])];
  report.part3_news[0].publish_time = "2026-08-08T23:59:59+08:00";
  report.part3_news[0].verification_status = "verified";

  assert.throws(
    () => validateReport(report, "2026-08-09.json"),
    /part3_news\[0\]\.publish_time is outside its validation window/,
  );
});

test("non-allowlisted legacy reports still reject publish times outside their windows", () => {
  const filename = "2026-07-10.json";
  const report = JSON.parse(fs.readFileSync(path.join(process.cwd(), "data", filename), "utf8"));
  report.part3_news[0].publish_time = "2026-07-09T23:59:59+08:00";

  assert.throws(
    () => validateReport(report, filename),
    /part3_news\[0\]\.publish_time is outside its validation window/,
  );
});

test("historical publish-window exceptions only allow their recorded values", () => {
  const filename = "2026-07-11.json";
  const report = JSON.parse(fs.readFileSync(path.join(process.cwd(), "data", filename), "utf8"));
  report.part3_news[0].publish_time = "2026-07-09T20:00:00+08:00";

  assert.throws(
    () => validateReport(report, filename),
    /part3_news\[0\]\.publish_time is outside its validation window/,
  );
});

test("URL verification counts must reconcile", () => {
  const filename = "2026-08-08.json";
  const report = JSON.parse(fs.readFileSync(path.join(process.cwd(), "data", filename), "utf8"));
  report.search_log.url_verification.passed = 7;

  assert.throws(
    () => validateReport(report, filename),
    /search_log\.url_verification\.checked must equal passed \+ failed/,
  );
});

test("complete collection can publish zero sources or results but failed collection cannot", () => {
  const complete = makeFutureReport();
  for (const part of ["part1", "part2", "part3"]) {
    complete.search_log[`${part}_sources_checked`] = [];
  }
  assert.doesNotThrow(() => validateReport(complete, "2026-08-09.json"));

  for (const part of ["part1", "part2", "part3"]) {
    const failed = makeFutureReport();
    failed.search_log[`${part}_searched`] = false;
    assert.throws(
      () => validateReport(failed, "2026-08-09.json"),
      new RegExp(`search_log\\.${part}_searched must be true`),
    );
  }

  const failedX = makeFutureReport();
  failedX.search_log.part2_channel = "failed";
  assert.throws(
    () => validateReport(failedX, "2026-08-09.json"),
    /search_log\.part2_channel must be twscrape or playwright/,
  );
});

test("unverified source-only cards require a visible reason and audit coverage", () => {
  const source = JSON.parse(fs.readFileSync(path.join(process.cwd(), "data", "2026-08-07.json"), "utf8"));
  const report = makeFutureReport();
  const item = structuredClone(source.part3_news[0]);
  item.publish_time = "2026-08-09";
  delete item.excerpt;
  delete item.interpretation;
  delete item.importance;
  report.part3_news = [item];

  assert.throws(
    () => validateReport(report, "2026-08-09.json"),
    /part3_news\[0\]\.verification_status is required/,
  );

  item.verification_status = "unverified";
  assert.throws(
    () => validateReport(report, "2026-08-09.json"),
    /part3_news\[0\]\.verification_note must be a non-empty string/,
  );

  item.verification_note = "原始页面暂时无法访问，仅保留标题和来源等待复核。";
  assert.throws(
    () => validateReport(report, "2026-08-09.json"),
    /url_verification\.failures must list unverified URL/,
  );
  report.search_log.url_verification.checked += 1;
  report.search_log.url_verification.failed += 1;
  report.search_log.url_verification.failures.push({
    url: item.url,
    reason: item.verification_note,
  });
  assert.doesNotThrow(() => validateReport(report, "2026-08-09.json"));

  report.search_log.url_verification = {
    checked: 10,
    passed: 10,
    failed: 0,
    failures: [],
  };
  assert.throws(
    () => validateReport(report, "2026-08-09.json"),
    /url_verification\.failed must cover unverified signals/,
  );
});

test("unverified source labels are rendered by signal cards", () => {
  const card = fs.readFileSync(
    path.join(process.cwd(), "components", "signal-card.tsx"),
    "utf8",
  );
  assert.match(card, /verificationStatus === "unverified"/);
  assert.match(card, /来源未核验/);
  assert.match(card, /verificationNote/);
});

test("reports from 2026-08-09 reject replacement characters", () => {
  const report = makeFutureReport();
  report.summary = "含有\ufffd的测试文本";

  assert.throws(
    () => validateReport(report, "2026-08-09.json"),
    /2026-08-09\.json: \$\.summary must not contain U\+FFFD replacement character/,
  );
});

test("daily JSON archive has no missing calendar dates", () => {
  const dates = loadReports().map((report) => report.date);
  for (let index = 1; index < dates.length; index += 1) {
    const previous = Date.parse(`${dates[index - 1]}T00:00:00Z`);
    const current = Date.parse(`${dates[index]}T00:00:00Z`);
    assert.equal(current - previous, 86_400_000, `missing daily JSON between ${dates[index - 1]} and ${dates[index]}`);
  }
});

test("every legacy daily HTML date has a JSON report", () => {
  const reportDates = new Set(loadReports().map((report) => report.date));
  const legacyDir = path.join(process.cwd(), "Historical_Daily_Reports");
  const legacyDates = fs.readdirSync(legacyDir)
    .map((filename) => /^mining_people_broadcast_x_digest_(\d{4}-\d{2}-\d{2})\.html$/.exec(filename)?.[1])
    .filter(Boolean);

  assert.ok(legacyDates.length > 0, "no legacy daily HTML files were detected");
  for (const date of legacyDates) {
    assert.ok(reportDates.has(date), `legacy HTML ${date} has no JSON report`);
  }
});

test("the six migrated JSON reports preserve every linked legacy news card", () => {
  const reports = new Map(loadReports().map((report) => [report.date, report]));
  for (const date of ["2026-06-30", "2026-07-01", "2026-07-02", "2026-07-03", "2026-07-04", "2026-07-05"]) {
    const filename = path.join(process.cwd(), "Historical_Daily_Reports", `mining_people_broadcast_x_digest_${date}.html`);
    const html = fs.readFileSync(filename, "utf8");
    const newsSection = /<section id="news"[\s\S]*?<\/section>/.exec(html)?.[0] ?? "";
    const linkedNewsCount = (newsSection.match(/<h3><a href=/g) ?? []).length;
    assert.equal(reports.get(date)?.part3_news.length, linkedNewsCount, `${date} migrated news count differs from legacy HTML`);
  }
});

test("every rendered signal has a reachable source shape", () => {
  const reports = loadReports();
  for (const report of reports) {
    const signals = [
      ...report.part1_broadcasts,
      ...report.part2_x_posts,
      ...report.part3_news,
    ];
    for (const signal of signals) {
      assert.ok(signal.metal_tags.length > 0);
      if (signal.primary_metal !== undefined) {
        assert.ok(signal.metal_tags.includes(signal.primary_metal));
      }
      assert.match(signal.url, /^https?:\/\//);
    }
  }
});

test("ACG is rendered once under copper while retaining its related metal tags", () => {
  const report = loadReports().find((item) => item.date === "2026-07-14");
  const acg = report?.part3_news.find((item) => item.source === "ACG Metals / RNS");

  assert.ok(acg, "ACG Metals signal is missing");
  assert.equal(acg.primary_metal, "copper");
  assert.deepEqual(acg.metal_tags, ["gold", "silver", "copper"]);
});

test("archive search index includes signal fact, interpretation, and importance", () => {
  const reports = fs.readFileSync(path.join(process.cwd(), "lib", "reports.ts"), "utf8");
  const searchIndex = /searchText:[\s\S]*?stats: getReportStats/.exec(reports)?.[0] ?? "";

  assert.match(searchIndex, /signal\.fact/);
  assert.match(searchIndex, /signal\.interpretation/);
  assert.match(searchIndex, /signal\.importance/);
});

test("home and daily pages group signals only by primary metal", () => {
  for (const filename of ["app/page.tsx", "app/daily/[date]/page.tsx"]) {
    const source = fs.readFileSync(path.join(process.cwd(), filename), "utf8");
    assert.match(source, /signal\.primaryMetal === metal/, `${filename} must group by primary metal`);
    assert.doesNotMatch(source, /signal\.metalTags\.includes\(metal\)/, `${filename} repeats multi-metal signals`);
  }
});

test("metal modules use the copper, gold, silver display order", () => {
  const reports = fs.readFileSync(path.join(process.cwd(), "lib/reports.ts"), "utf8");
  assert.match(reports, /METALS: Metal\[\] = \["copper", "gold", "silver"\]/);

  for (const filename of ["app/page.tsx", "app/daily/[date]/page.tsx"]) {
    const source = fs.readFileSync(path.join(process.cwd(), filename), "utf8");
    assert.match(source, /METALS\.map\(/, `${filename} must use the shared metal order`);
  }
});

test("inventory navigation reveals a labeled new-tab link", () => {
  const header = fs.readFileSync(path.join(process.cwd(), "components/site-header.tsx"), "utf8");
  assert.match(header, /aria-controls="inventory-menu-panel"/);
  assert.match(header, /<span>三大交易所铜库存<\/span>/);
  assert.match(header, /href=\{INVENTORY_URL\} rel="noopener noreferrer" target="_blank"/);
});

test("SEO metadata declares crawl routes, self canonicals, and daily Article fields", () => {
  const robots = fs.readFileSync(path.join(process.cwd(), "app/robots.ts"), "utf8");
  const sitemap = fs.readFileSync(path.join(process.cwd(), "app/sitemap.ts"), "utf8");
  const layout = fs.readFileSync(path.join(process.cwd(), "app/layout.tsx"), "utf8");
  const archive = fs.readFileSync(path.join(process.cwd(), "app/archive/page.tsx"), "utf8");
  const daily = fs.readFileSync(path.join(process.cwd(), "app/daily/[date]/page.tsx"), "utf8");
  const historicalTc = fs.readFileSync(path.join(process.cwd(), "app/historical-tc/page.tsx"), "utf8");

  assert.match(robots, /allow:\s*"\/"/);
  assert.match(robots, /sitemap:\s*`\$\{SITE_URL\}\/sitemap\.xml`/);
  assert.match(sitemap, /getReports\(\)/);
  assert.match(sitemap, /\/daily\/\$\{report\.date\}/);
  assert.match(layout, /canonical:\s*"\/"/);
  assert.match(archive, /canonical:\s*"\/archive"/);
  assert.match(daily, /canonical:\s*`\/daily\/\$\{report\.date\}`/);
  assert.match(daily, /"@type": "Article"/);
  assert.match(daily, /headline:\s*articleTitle/);
  assert.match(daily, /description:\s*getReportSummary\(report\)/);
  assert.match(daily, /datePublished:\s*publishedAt/);
  assert.match(sitemap, /\/historical-tc/);
  assert.match(historicalTc, /canonical:\s*"\/historical-tc"/);
});
