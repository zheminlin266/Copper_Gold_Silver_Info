import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { validateWeeklyReport } from "../scripts/validate-content.mjs";

const filename = "2026-11-09.json";
function sample() {
  return JSON.parse(fs.readFileSync(new URL(`../data/weekly/${filename}`, import.meta.url), "utf8"));
}

test("weekly reports require the correct period and source links with no editorial event cap", () => {
  const report = sample();
  const event = report.copper_events[0];
  for (let index = 0; index < 60; index += 1) {
    report.copper_events.push({ ...event, id: `additional-${index}` });
  }
  assert.equal(validateWeeklyReport(report, filename), report);
  assert.throws(() => validateWeeklyReport({ ...report, week_end: "2026-11-16" }, filename), /Monday–Sunday/);
  assert.throws(() => validateWeeklyReport(report, "2026-11-16.json"), /filename/);
  event.date = "2026-11-16";
  assert.throws(() => validateWeeklyReport(report, filename), /outside the week/);
  event.date = "2026-11-12";
  event.sources = [];
  assert.throws(() => validateWeeklyReport(report, filename), /source links/);
});

test("weekly synthesis can cite only unique copper event IDs", () => {
  const report = sample();
  report.supply_analysis[0].event_ids = [report.gold_briefs[0].id];
  assert.throws(() => validateWeeklyReport(report, filename), /supply_analysis evidence/);
  report.supply_analysis[0].event_ids = [report.copper_events[0].id];
  report.gold_briefs[0].id = report.copper_events[0].id;
  assert.throws(() => validateWeeklyReport(report, filename), /duplicate/);
});

test("weekly copper events accept an ungrouped list and validate legacy group labels", () => {
  const report = sample();
  for (const event of report.copper_events) delete event.group;
  assert.equal(validateWeeklyReport(report, filename), report);

  report.copper_events[0].group = "unknown";
  assert.throws(() => validateWeeklyReport(report, filename), /invalid copper_events\[0\]\.group/);
});
