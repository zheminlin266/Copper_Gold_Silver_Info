// Run against a production build: node scripts/check-archive-indexing.mjs http://localhost:3107
import assert from "node:assert/strict";
import { archivePagePath, REPORTS_PER_PAGE } from "../lib/archive-pagination.ts";

const base = process.argv[2];
assert.ok(base, "Pass the URL of a running production build");
const headers = { "User-Agent": "Googlebot" };
const sitemap = await fetch(new URL("/sitemap.xml", base), { headers });
assert.equal(sitemap.status, 200, "sitemap status");
const dailyUrls = [...(await sitemap.text()).matchAll(/<loc>([^<]+\/daily\/\d{4}-\d{2}-\d{2})<\/loc>/g)]
  .map((match) => new URL(match[1]));
assert.ok(dailyUrls.length, "sitemap has daily reports");
const origin = dailyUrls[0].origin;
const expected = dailyUrls.map((url) => url.pathname).sort().reverse();
const pageCount = Math.ceil(expected.length / REPORTS_PER_PAGE);
const found = [];

for (let page = 1; page <= pageCount; page += 1) {
  const path = archivePagePath(page);
  const response = await fetch(new URL(path, base), { headers, redirect: "manual" });
  assert.equal(response.status, 200, path);
  assert.doesNotMatch(response.headers.get("x-robots-tag") ?? "", /noindex/i, path);
  const html = await response.text();
  assert.doesNotMatch(html, /<meta[^>]+name="robots"[^>]+content="[^"]*noindex/i, path);
  const canonicals = [...html.matchAll(/<link rel="canonical" href="([^"]+)"/g)].map((match) => match[1]);
  assert.deepEqual(canonicals, [origin + path], `${path} self canonical`);
  const reports = [...html.matchAll(/<a\b[^>]*href="(\/daily\/\d{4}-\d{2}-\d{2})"/g)]
    .map((match) => match[1]);
  assert.deepEqual(reports, expected.slice((page - 1) * REPORTS_PER_PAGE, page * REPORTS_PER_PAGE), `${path} initial HTML`);
  found.push(...reports);
  const links = [...html.matchAll(/<a\b[^>]*href="(\/archive(?:\/\d+)?)"/g)].map((match) => match[1]);
  if (page > 1) assert.ok(links.includes(archivePagePath(page - 1)), `${path} previous link`);
  if (page < pageCount) assert.ok(links.includes(archivePagePath(page + 1)), `${path} next link`);
  assert.ok(!links.includes("/archive/0") && !links.includes(archivePagePath(pageCount + 1)), `${path} boundaries`);
}

assert.deepEqual(found, expected, "Every daily report is linked once across archive pages without JavaScript");
for (const path of ["/archive/0", "/archive/1", "/archive/02", "/archive/-2", "/archive/1.5", "/archive/NaN", "/archive/2/extra", archivePagePath(pageCount + 1)]) {
  const response = await fetch(new URL(path, base), { headers, redirect: "manual" });
  assert.equal(response.status, 404, `${path} must not create duplicate or empty indexable pages`);
}
console.log(`Passed: ${pageCount} archive pages, ${found.length} daily links, self canonicals, pagination and invalid-route checks.`);
