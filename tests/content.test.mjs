import assert from "node:assert/strict";
import test from "node:test";

import { loadReports } from "../scripts/validate-content.mjs";

test("all daily reports are valid and uniquely dated", () => {
  const reports = loadReports();
  const dates = reports.map((report) => report.date);
  assert.equal(new Set(dates).size, dates.length);
  assert.deepEqual(dates, [...dates].sort());
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
