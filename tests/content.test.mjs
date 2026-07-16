import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

import { getArchivePage, REPORTS_PER_PAGE } from "../lib/archive-pagination.ts";
import { loadReports, validateReport } from "../scripts/validate-content.mjs";

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

test("all daily reports are valid and uniquely dated", () => {
  const reports = loadReports();
  const dates = reports.map((report) => report.date);
  assert.equal(new Set(dates).size, dates.length);
  assert.deepEqual(dates, [...dates].sort());
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

test("home and daily pages group signals only by primary metal", () => {
  for (const filename of ["app/page.tsx", "app/daily/[date]/page.tsx"]) {
    const source = fs.readFileSync(path.join(process.cwd(), filename), "utf8");
    assert.match(source, /signal\.primaryMetal === metal/, `${filename} must group by primary metal`);
    assert.doesNotMatch(source, /signal\.metalTags\.includes\(metal\)/, `${filename} repeats multi-metal signals`);
  }
});

test("SEO metadata declares crawl routes, self canonicals, and daily Article fields", () => {
  const robots = fs.readFileSync(path.join(process.cwd(), "app/robots.ts"), "utf8");
  const sitemap = fs.readFileSync(path.join(process.cwd(), "app/sitemap.ts"), "utf8");
  const layout = fs.readFileSync(path.join(process.cwd(), "app/layout.tsx"), "utf8");
  const archive = fs.readFileSync(path.join(process.cwd(), "app/archive/page.tsx"), "utf8");
  const daily = fs.readFileSync(path.join(process.cwd(), "app/daily/[date]/page.tsx"), "utf8");

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
});
