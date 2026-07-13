import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

import { loadReports } from "../scripts/validate-content.mjs";

test("all daily reports are valid and uniquely dated", () => {
  const reports = loadReports();
  const dates = reports.map((report) => report.date);
  assert.equal(new Set(dates).size, dates.length);
  assert.deepEqual(dates, [...dates].sort());
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
      assert.match(signal.url, /^https?:\/\//);
    }
  }
});
