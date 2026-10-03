import test from "node:test";
import assert from "node:assert/strict";
import { validateReport, loadReports } from "../scripts/validate-content.mjs";

function reportFor(kind, date = "2026-10-03") {
  const windows = Object.fromEntries(["part1", "part2", "part3"].map((part) => [part, {
    start: `${part === "part1" ? new Date(Date.parse(`${date}T00:00:00Z`) - 2 * 86400000).toISOString().slice(0, 10) : date}T00:00:00+08:00`,
    end: `${date}T23:59:59+08:00`,
  }]));
  const item = {
    url: "https://example.com/source", metal_tags: ["copper"], primary_metal: "copper",
    supply_demand: "supply", verification_status: "unverified", verification_note: "Source inaccessible",
    ...(kind === "broadcast" ? { title: "Source title", summary: "Source title", source_type: "podcast", publish_date: date }
      : kind === "x" ? { author: "Example", handle: "@example", publish_time: date }
        : { title: "Source title", source: "Example", language: "en", publish_time: date }),
  };
  const report = {
    schema_version: 3, date, report_time: `${date}T07:00:00+08:00`, summary: "铜供给变化。", windows,
    part1_broadcasts: [], part2_x_posts: [], part3_news: [],
    search_log: {
      part1_searched: true, part1_sources_checked: [], part1_result: "completed",
      part2_searched: true, part2_channel: "playwright", part2_sources_checked: ["Example"], part2_result: "completed",
      part2_coverage: { status: "complete", accounts_total: 1, accounts_completed: 1, accounts_failed: 0,
        attempted_channels: ["playwright"], selected_channel: "playwright", channel_errors: [], notes: "completed" },
      part3_searched: true, part3_sources_checked: [], part3_result: "completed",
      url_verification: { checked: 1, passed: 0, failed: 1, failures: [{ url: item.url, reason: "Source inaccessible" }] },
    },
    dedup_log: { part1_deduped_urls: [], part3_deduped_events: [] },
  };
  report[{ broadcast: "part1_broadcasts", x: "part2_x_posts", news: "part3_news" }[kind]].push(item);
  return { report, item };
}

for (const kind of ["broadcast", "x", "news"]) {
  test(`new ${kind} unverified cards enforce source-only contract`, () => {
    const { report, item } = reportFor(kind);
    const validate = () => validateReport(report, `${report.date}.json`);
    assert.doesNotThrow(validate);
    const claim = { claim: "Claim", evidence: "Unrelated quote", source_url: item.url,
      evidence_type: "release", period: "2026", unit: "status", value: "advanced" };
    for (const [key, value] of Object.entries({ detail: "Narrative", excerpt: "Narrative", interpretation: "Judgment", importance: "Judgment", claims: [claim] })) {
      item[key] = value;
      assert.throws(validate, /source-only|Schema/);
      delete item[key];
    }
    item.claims = [];
    assert.doesNotThrow(validate);
    delete item.claims;
    if (kind === "broadcast") {
      item.summary = "Source title and availability note";
      assert.throws(validate, /exactly equal broadcast title/);
      item.summary = item.title;
      assert.doesNotThrow(validate);
    }
  });
}

test("new verified X/news require explicit facts, not interpretation fallback", () => {
  for (const kind of ["x", "news"]) {
    const { report, item } = reportFor(kind);
    item.verification_status = "verified";
    report.search_log.url_verification = { checked: 1, passed: 1, failed: 0, failures: [] };
    assert.doesNotThrow(() => validateReport(report, `${report.date}.json`));
    item.interpretation = "Judgment only";
    assert.throws(() => validateReport(report, `${report.date}.json`), /excerpt/);
    item.excerpt = "Explicit source facts";
    assert.doesNotThrow(() => validateReport(report, `${report.date}.json`));
  }
});

test("historical narratives remain compatible and published reports validate unchanged", () => {
  for (const kind of ["broadcast", "x", "news"]) {
    const { report, item } = reportFor(kind, "2026-10-02");
    if (kind === "broadcast") item.summary = "Historical factual summary";
    else item.interpretation = "Historical explanation-only card";
    assert.doesNotThrow(() => validateReport(report, `${report.date}.json`));
  }
  assert.ok(loadReports().length > 0);
});
